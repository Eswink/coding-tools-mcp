//go:build windows && !guest

package main

import (
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sync/atomic"
	"time"

	"github.com/Microsoft/go-winio"
	"github.com/Microsoft/go-winio/pkg/guid"
	"github.com/Microsoft/hcsshim/internal/cow"
	"github.com/Microsoft/hcsshim/internal/gcs/prot"
	hcsschema "github.com/Microsoft/hcsshim/internal/hcs/schema2"
	"github.com/Microsoft/hcsshim/internal/hcsoci"
	"github.com/Microsoft/hcsshim/internal/layers"
	"github.com/Microsoft/hcsshim/internal/resources"
	"github.com/Microsoft/hcsshim/internal/schemaversion"
	"github.com/Microsoft/hcsshim/internal/uvm"
	"github.com/Microsoft/hcsshim/pkg/ociwclayer"
	"github.com/opencontainers/runtime-spec/specs-go"
	"golang.org/x/sys/windows"
)

const workspace = `C:\Users\ContainerUser\ctm-workspace`
const powershell = `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`
const denyHv = "D:P(D;;FA;;;WD)"

var imageLayers = []struct {
	digest string
	size   int64
}{
	{"97e96e9cbeb16024139f78dc6ed542a7cf572ac80d8cea50a3308368094c4574", 1482371926},
	{"67f39c55a3f42bc0569099cebb32cef6688837ca694dfacaa00053810cb810d6", 914397517},
}

func verifyFile(path, digest string, size int64) error {
	f, e := os.Open(path)
	if e != nil {
		return e
	}
	h := sha256.New()
	n, e := io.Copy(h, f)
	e = errors.Join(e, f.Close())
	if n != size || hex.EncodeToString(h.Sum(nil)) != digest {
		return errors.Join(e, errors.New("pinned file mismatch"))
	}
	return e
}
func importLayers(root string) (err error) {
	for i, l := range imageLayers {
		if err = verifyFile(filepath.Join(root, fmt.Sprintf("layer%d.gz", i)), l.digest, l.size); err != nil {
			return
		}
	}
	privileges := []string{winio.SeBackupPrivilege, winio.SeRestorePrivilege}
	if err = winio.EnableProcessPrivileges(privileges); err != nil {
		return
	}
	defer func() { err = errors.Join(err, winio.DisableProcessPrivileges(privileges)) }()
	ctx, stop := context.WithTimeout(context.Background(), 10*time.Minute)
	defer stop()
	parents := []string{}
	for i := range imageLayers {
		path := filepath.Join(root, fmt.Sprintf("layer%d", i))
		if _, e := os.Lstat(path); !os.IsNotExist(e) {
			return errors.New("import destination exists or uncertain")
		}
		f, e := os.Open(filepath.Join(root, fmt.Sprintf("layer%d.gz", i)))
		if e != nil {
			return e
		}
		z, e := gzip.NewReader(f)
		if e != nil {
			return errors.Join(e, f.Close())
		}
		_, e = ociwclayer.ImportLayerFromTar(ctx, z, path, parents)
		err = errors.Join(e, z.Close(), f.Close())
		if err != nil {
			return
		}
		parents = append(parents, path)
	}
	return nil
}
func buildOptions(id string) *uvm.OptionsWCOW {
	o := uvm.NewDefaultOptionsWCOW(id, "ctm-windows-vm-session")
	o.ProcessorCount = 2
	o.MemorySizeInMB = 2048
	o.NoWritableFileShares = true
	o.NoDirectMap = true
	o.NoInheritHostTimezone = true
	return o
}
func configureBrokerPolicy(o *uvm.OptionsWCOW, sid string) error {
	s, e := windows.StringToSid(sid)
	if e != nil || s.String() != sid {
		return errors.New("broker SID invalid")
	}
	ids := []guid.GUID{prot.WindowsGcsHvsockServiceID}
	for p := uint32(prot.LinuxGcsVsockPort + 1); p <= prot.LinuxGcsVsockPort+6; p++ {
		ids = append(ids, winio.VsockServiceID(p))
	}
	if len(o.AdditionalHyperVConfig) != 0 {
		return errors.New("unexpected initial service entries")
	}
	for _, id := range ids {
		o.AdditionalHyperVConfig[id.String()] = hcsschema.HvSocketServiceConfig{BindSecurityDescriptor: "D:P(A;;FA;;;" + sid + ")", ConnectSecurityDescriptor: denyHv}
	}
	return nil
}

type ownedVM struct {
	guestReady                  atomic.Bool
	id, runtimeID, root, assets string
	vm                          *uvm.UtilityVM
	container                   cow.Container
	resources                   *resources.Resources
	processes                   []*guestProcess
	guest                       *guestProcess
	synthetic                   *syntheticRoot
	receipt                     Cleanup
}

func (v *ownedVM) record(stage string, e error) {
	if e != nil {
		msg := stage + ": " + e.Error()
		if len(msg) > 2048 {
			msg = msg[:2048]
		}
		v.receipt.Errors = append(v.receipt.Errors, msg)
	}
}
func (v *ownedVM) start(ctx context.Context, r Request, emit func(string, *GuestResult, *Cleanup, string) error) error {
	paths := []string{filepath.Join(v.assets, "layer1"), filepath.Join(v.assets, "layer0"), filepath.Join(v.root, "scratch")}
	if e := os.Mkdir(paths[2], 0700); e != nil {
		return e
	}
	o := buildOptions(v.id)
	user, e := windows.GetCurrentProcessToken().GetTokenUser()
	if e != nil {
		return e
	}
	if e = configureBrokerPolicy(o, user.User.Sid.String()); e != nil {
		return e
	}
	o.BootFiles, e = layers.GetWCOWUVMBootFilesFromLayers(ctx, nil, paths)
	if e != nil {
		return e
	}
	v.vm, e = uvm.CreateWCOW(ctx, o)
	if e != nil {
		return fmt.Errorf("create outcome uncertain: %w", e)
	}
	v.runtimeID = v.vm.RuntimeID().String()
	if e = v.vm.Start(ctx); e != nil {
		return e
	}
	wl, e := layers.ParseWCOWLayers(nil, paths)
	if e != nil {
		return e
	}
	v.container, v.resources, e = hcsoci.CreateContainer(ctx, &hcsoci.CreateOptions{ID: v.id + "-guest", Owner: "ctm-windows-vm-session", HostingSystem: v.vm,
		SchemaVersion: schemaversion.SchemaV21(), Spec: containerSpec(paths), WCOWLayers: wl, DoNotReleaseResourcesOnFailure: true})
	if e != nil {
		return e
	}
	if e = v.container.Start(ctx); e != nil {
		return e
	}
	bootstrap := `"` + powershell + `" -NoLogo -NoProfile -NonInteractive -Command "$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';$w='` + workspace + `';[IO.Directory]::CreateDirectory($w)|Out-Null;$f=[IO.File]::Create($w+'\runtime.zip');try{[Console]::OpenStandardInput().CopyTo($f)}finally{$f.Dispose()};Expand-Archive -LiteralPath ($w+'\runtime.zip') -DestinationPath $w;[Console]::WriteLine('CTM_VM_BOOTSTRAP');exit 23"`
	p, e := openGuestProcess(ctx, v.container, bootstrap, `C:\`)
	if p != nil {
		v.processes = append(v.processes, p)
	}
	if e != nil {
		return e
	}
	bundle, e := os.Open(filepath.Join(v.assets, "runtime.zip"))
	if e != nil {
		return e
	}
	e = errors.Join(p.bootstrap(ctx, bundle), bundle.Close())
	if e != nil {
		return e
	}
	p, e = openGuestProcess(ctx, v.container, `"`+workspace+`\guest.exe" --guest`, workspace)
	if p != nil {
		v.processes = append(v.processes, p)
		v.guest = p
	}
	if e != nil {
		return e
	}
	if e = p.startFrames(ctx); e != nil {
		return e
	}
	if e = emit("running", nil, nil, ""); e != nil {
		return e
	}
	request := GuestRequest{Request: r, DataBase64: encodeBytes(v.synthetic.data), InputSHA256: v.synthetic.inputSHA}
	result, e := p.exchange(ctx, request)
	if e != nil {
		return e
	}
	if e = v.synthetic.acceptGuest(result); e != nil {
		return e
	}
	if r.Fixture == "runtimes" {
		if len(result.Cases) != 4 || result.ChildAlive {
			return errors.New("runtime inventory")
		}
		for _, c := range result.Cases {
			if !c.Passed {
				return errors.New("stock runtime failed")
			}
		}
	} else if !result.ChildAlive || len(result.Cases) != 0 {
		return errors.New("live descendant missing")
	}
	v.guestReady.Store(true)
	return emit("guest", &result, nil, "")
}
func (v *ownedVM) close(cancelled bool) {
	c := &v.receipt
	if v.vm == nil {
		v.record("whole_vm", errors.New("creation/handle outcome uncertain"))
		return
	}
	stop, end := context.WithTimeout(context.Background(), 45*time.Second)
	e := v.vm.Terminate(stop)
	end()
	c.TerminateOK = e == nil
	v.record("terminate", e)
	wait, end := context.WithTimeout(context.Background(), 45*time.Second)
	e = v.vm.WaitCtx(wait)
	end()
	c.WholeVMExited = e == nil
	v.record("whole_vm_wait", e)
	if !c.WholeVMExited {
		return
	}
	e = v.vm.ExitError()
	c.ExitOK = e == nil
	v.record("exit_reason", e)
	c.GuestIOJoined = true
	for _, p := range v.processes {
		joined, e := p.close()
		c.GuestIOJoined = c.GuestIOJoined && joined
		v.record("guest_io", e)
	}
	closeCtx, end := context.WithTimeout(context.Background(), 30*time.Second)
	defer end()
	var closing error
	if v.container != nil {
		closing = errors.Join(closing, v.container.Close())
	}
	if v.resources != nil {
		v.resources.SetLayers(nil)
		closing = errors.Join(closing, resources.ReleaseResources(closeCtx, v.resources, nil, true))
	}
	closing = errors.Join(closing, v.vm.CloseCtx(closeCtx))
	c.CloseOK = closing == nil
	v.record("close", closing)
	if lifecycleComplete(*c) {
		v.record("quarantine", v.synthetic.finish(c, cancelled))
	}
	v.record("synthetic_handles", v.synthetic.close())
}

func containerSpec(paths []string) *specs.Spec {
	return &specs.Spec{Windows: &specs.Windows{LayerFolders: paths}}
}
func encodeBytes(data []byte) string { return base64.StdEncoding.EncodeToString(data) }

type bundleInfo struct {
	Source        string `json:"source"`
	BrokerSHA256  string `json:"broker_sha256"`
	GuestSHA256   string `json:"guest_sha256"`
	Node          string `json:"node"`
	Pwsh          string `json:"pwsh"`
	ImageManifest string `json:"image_manifest"`
	RuntimeSHA256 string `json:"runtime_sha256"`
}

func validateAssets(root string) error {
	f, e := os.Open(filepath.Join(root, "bundle.json"))
	if e != nil {
		return e
	}
	b, e := io.ReadAll(io.LimitReader(f, 65537))
	e = errors.Join(e, f.Close())
	if e != nil {
		return e
	}
	var info bundleInfo
	if e = decodeStrict(b, &info); e != nil {
		return e
	}
	if info.Source != buildSource || info.Node != "v22.23.3" || info.Pwsh != "7.6.6" || info.ImageManifest != "sha256:22505496dd4229dba63453ba0c6dc31c06fd3e11810e5b8e429aa6b16dab2457" {
		return errors.New("fixed runtime/source/image mismatch")
	}
	bundle := filepath.Join(root, "runtime.zip")
	st, e := os.Stat(bundle)
	if e != nil {
		return e
	}
	if st.Size() > 300*1024*1024 {
		return errors.New("runtime bundle bound")
	}
	return verifyFile(bundle, info.RuntimeSHA256, st.Size())
}
