//go:build windows && !fixture

package main

import (
	"bytes"
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"
	"unicode/utf16"

	"github.com/Microsoft/go-winio"
	"github.com/Microsoft/go-winio/pkg/guid"
	"github.com/Microsoft/hcsshim/internal/cow"
	hcsschema "github.com/Microsoft/hcsshim/internal/hcs/schema2"
	"github.com/Microsoft/hcsshim/internal/hcsoci"
	"github.com/Microsoft/hcsshim/internal/layers"
	"github.com/Microsoft/hcsshim/internal/resources"
	"github.com/Microsoft/hcsshim/internal/schemaversion"
	"github.com/Microsoft/hcsshim/internal/uvm"
	"github.com/Microsoft/hcsshim/pkg/ociwclayer"
	"github.com/opencontainers/runtime-spec/specs-go"
)

const workspace = `C:\Users\ContainerUser\ctm-workspace`
const powershell = `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`
const outputLimit = 65536

var imageLayers = []struct {
	digest string
	size   int64
}{
	{"97e96e9cbeb16024139f78dc6ed542a7cf572ac80d8cea50a3308368094c4574", 1482371926},
	{"67f39c55a3f42bc0569099cebb32cef6688837ca694dfacaa00053810cb810d6", 914397517},
}

type caseResult struct {
	Name     string `json:"name"`
	Stdout   string `json:"stdout"`
	Stderr   string `json:"stderr"`
	ExitCode int    `json:"exit_code"`
	Passed   bool   `json:"passed"`
}
type report struct {
	Schema              int          `json:"schema"`
	Source              string       `json:"source"`
	ID                  string       `json:"owned_uvm_id"`
	RuntimeID           string       `json:"runtime_id"`
	Stage               string       `json:"stage"`
	Cases               []caseResult `json:"cases"`
	Errors              []string     `json:"errors"`
	TerminateOK         bool         `json:"terminate_ok"`
	WholeVMExited       bool         `json:"whole_vm_exited"`
	ExitOK              bool         `json:"exit_reason_ok"`
	CloseOK             bool         `json:"close_ok"`
	RuntimePassed       bool         `json:"runtime_passed"`
	NetworkDenied       bool         `json:"network_denial_proven"`
	WorkspaceIntegrated bool         `json:"workspace_integration"`
	ProductionAdmission bool         `json:"production_admission"`
	DataRetained        bool         `json:"owned_data_retained"`
}

func (r *report) record(stage string, err error) {
	if err != nil {
		r.Errors = append(r.Errors, stage+": "+err.Error())
	}
}
func complete(r report) bool {
	return r.RuntimePassed && r.TerminateOK && r.WholeVMExited && r.ExitOK && r.CloseOK && len(r.Errors) == 0
}
func writeReport(path string, v any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	if len(b) > 1048576 {
		return errors.New("report bound exceeded")
	}
	return os.WriteFile(path, b, 0600)
}
func verifyFile(path, digest string, size int64) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	h := sha256.New()
	n, err := io.Copy(h, f)
	if err != nil {
		return err
	}
	if n != size || hex.EncodeToString(h.Sum(nil)) != digest {
		return errors.New("pinned layer mismatch")
	}
	return nil
}
func importLayers(root string) (err error) {
	// No privileges are enabled until BOTH immutable blobs pass verification.
	for i, l := range imageLayers {
		if err = verifyFile(filepath.Join(root, fmt.Sprintf("layer%d.gz", i)), l.digest, l.size); err != nil {
			return err
		}
	}
	privs := []string{winio.SeBackupPrivilege, winio.SeRestorePrivilege}
	if err = winio.EnableProcessPrivileges(privs); err != nil {
		return err
	}
	defer func() { err = errors.Join(err, winio.DisableProcessPrivileges(privs)) }()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()
	parents := []string{}
	for i := range imageLayers {
		path := filepath.Join(root, fmt.Sprintf("layer%d", i))
		if _, e := os.Lstat(path); !os.IsNotExist(e) {
			return errors.New("layer destination already exists")
		}
		f, e := os.Open(filepath.Join(root, fmt.Sprintf("layer%d.gz", i)))
		if e != nil {
			return e
		}
		z, e := gzip.NewReader(f)
		if e != nil {
			f.Close()
			return e
		}
		_, e = ociwclayer.ImportLayerFromTar(ctx, z, path, parents)
		err = errors.Join(e, z.Close(), f.Close())
		if err != nil {
			return err
		}
		parents = append(parents, path)
	}
	return nil
}
func buildOptions(id string) *uvm.OptionsWCOW {
	o := uvm.NewDefaultOptionsWCOW(id, "ctm-owned-boot-prototype")
	o.ProcessorCount = 2
	o.MemorySizeInMB = 2048
	o.NoWritableFileShares = true
	o.NoDirectMap = true
	o.NoInheritHostTimezone = true
	return o
}
func containerSpec(paths []string) *specs.Spec {
	return &specs.Spec{Windows: &specs.Windows{LayerFolders: paths}}
}
func encodedCommand(script string) string {
	u := utf16.Encode([]rune(script))
	b := make([]byte, len(u)*2)
	for i, v := range u {
		binary.LittleEndian.PutUint16(b[i*2:], v)
	}
	return `"` + powershell + `" -NoLogo -NoProfile -NonInteractive -EncodedCommand ` + base64.StdEncoding.EncodeToString(b)
}

type boundedOutput struct {
	buffer   bytes.Buffer // Named field prevents promoted ReadFrom from bypassing Write.
	overflow bool
}

func (b *boundedOutput) Len() int       { return b.buffer.Len() }
func (b *boundedOutput) String() string { return b.buffer.String() }

func (b *boundedOutput) Write(p []byte) (int, error) {
	n := len(p)
	room := outputLimit - b.Len()
	if n > room {
		b.overflow = true
		p = p[:room]
	}
	b.buffer.Write(p)
	return n, nil
}
func runGuest(ctx context.Context, host cow.ProcessHost, name, command, cwd, marker string, input io.Reader) (result caseResult, err error) {
	result.Name = name
	result.ExitCode = -1
	p, err := host.CreateProcess(ctx, &hcsschema.ProcessParameters{CommandLine: command, User: "ContainerUser", WorkingDirectory: cwd,
		Environment:     map[string]string{"POWERSHELL_TELEMETRY_OPTOUT": "1", "POWERSHELL_UPDATECHECK": "Off"},
		CreateStdInPipe: true, CreateStdOutPipe: true, CreateStdErrPipe: true})
	if err != nil {
		return result, err
	}
	defer func() { err = errors.Join(err, p.Close()) }()
	in, out, stderr := p.Stdio()
	if in == nil || out == nil || stderr == nil {
		return result, errors.New("missing HCS stdio")
	}
	var stdoutBuf, stderrBuf boundedOutput
	done := make(chan error, 4)
	go func() { _, e := io.Copy(&stdoutBuf, out); done <- e }()
	go func() { _, e := io.Copy(&stderrBuf, stderr); done <- e }()
	go func() {
		var e error
		if input != nil {
			_, e = io.Copy(in, input)
		}
		done <- errors.Join(e, p.CloseStdin(ctx))
	}()
	go func() { done <- p.Wait() }()
	for i := 0; i < 4; i++ {
		select {
		case e := <-done:
			err = errors.Join(err, e)
		case <-ctx.Done():
			return result, errors.Join(err, ctx.Err())
		}
	}
	result.Stdout = stdoutBuf.String()
	result.Stderr = stderrBuf.String()
	var e error
	result.ExitCode, e = p.ExitCode()
	err = errors.Join(err, e)
	if stdoutBuf.overflow || stderrBuf.overflow {
		err = errors.Join(err, errors.New("output overflow"))
	}
	result.Passed = err == nil && result.ExitCode == 23 && strings.Contains(result.Stdout, marker)
	if !result.Passed {
		err = errors.Join(err, errors.New("guest case did not meet exact marker/exit23 contract"))
	}
	return result, err
}
func runtimeCommands() []struct{ name, command, marker string } {
	ps := `$ErrorActionPreference='Stop';[IO.File]::WriteAllText('roundtrip-ps.txt','CTM_PS');if([IO.File]::ReadAllText('roundtrip-ps.txt') -cne 'CTM_PS'){exit 91};[Console]::WriteLine('CTM_PS_ENTRY '+$PSVersionTable.PSVersion);exit 23`
	pw := `$ErrorActionPreference='Stop';[IO.File]::WriteAllText('roundtrip-pwsh.txt','CTM_PWSH');if([IO.File]::ReadAllText('roundtrip-pwsh.txt') -cne 'CTM_PWSH'){exit 91};[Console]::WriteLine('CTM_PWSH_ENTRY '+$PSVersionTable.PSVersion);exit 23`
	return []struct{ name, command, marker string }{
		{"cmd", `C:\Windows\System32\cmd.exe /d /s /c ">roundtrip-cmd.txt echo CTM_CMD&& C:\Windows\System32\findstr.exe /x CTM_CMD roundtrip-cmd.txt&& echo CTM_CMD_ENTRY&& exit /b 23"`, "CTM_CMD_ENTRY"},
		{"windows-powershell", encodedCommand(ps), "CTM_PS_ENTRY"},
		{"node", `"` + workspace + `\node.exe" -e "const f=require('fs');f.writeFileSync('roundtrip-node.txt','CTM_NODE');if(f.readFileSync('roundtrip-node.txt','utf8')!=='CTM_NODE')process.exit(91);console.log('CTM_NODE_ENTRY '+process.version);process.exit(23)"`, "CTM_NODE_ENTRY"},
		{"pwsh", strings.Replace(encodedCommand(pw), powershell, workspace+`\pwsh\pwsh.exe`, 1), "CTM_PWSH_ENTRY"},
	}
}
func runPrototype(root string, r *report) (err error) {
	ctx, cancel := context.WithTimeout(context.Background(), 6*time.Minute)
	defer cancel()
	g, err := guid.NewV4()
	if err != nil {
		return err
	}
	r.ID = g.String()
	paths := []string{filepath.Join(root, "layer1"), filepath.Join(root, "layer0"), filepath.Join(root, "scratch")}
	if err = os.Mkdir(paths[2], 0700); err != nil {
		return err
	}
	o := buildOptions(r.ID)
	o.BootFiles, err = layers.GetWCOWUVMBootFilesFromLayers(ctx, nil, paths)
	if err != nil {
		return err
	}
	r.Stage = "create_uvm"
	vm, err := uvm.CreateWCOW(ctx, o)
	if err != nil {
		return fmt.Errorf("create outcome uncertain: %w", err)
	}
	r.RuntimeID = vm.RuntimeID().String()
	var container cow.Container
	var ownedResources *resources.Resources
	defer func() {
		stop, cancelStop := context.WithTimeout(context.Background(), 45*time.Second)
		defer cancelStop()
		e := vm.Terminate(stop)
		r.TerminateOK = e == nil
		r.record("terminate", e)
		wait, cancelWait := context.WithTimeout(context.Background(), 45*time.Second)
		defer cancelWait()
		e = vm.WaitCtx(wait)
		r.WholeVMExited = e == nil
		r.record("whole_vm_wait", e)
		if !r.WholeVMExited {
			return
		} // No close call can manufacture exit proof.
		e = vm.ExitError()
		r.ExitOK = e == nil
		r.record("exit_reason", e)
		closeCtx, cancelClose := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancelClose()
		if container != nil {
			r.record("container_close", container.Close())
		}
		if ownedResources != nil {
			// The guest and its attachments are gone; keep disk data, release only intrinsic address handle.
			ownedResources.SetLayers(nil)
			r.record("intrinsic_handle_release", resources.ReleaseResources(closeCtx, ownedResources, nil, true))
		}
		e = vm.CloseCtx(closeCtx)
		r.CloseOK = e == nil
		r.record("handle_close", e)
	}()
	r.Stage = "start_uvm"
	if err = vm.Start(ctx); err != nil {
		return err
	}
	wl, err := layers.ParseWCOWLayers(nil, paths)
	if err != nil {
		return err
	}
	r.Stage = "create_guest_container"
	container, ownedResources, err = hcsoci.CreateContainer(ctx, &hcsoci.CreateOptions{ID: r.ID + "-guest", Owner: "ctm-owned-boot-prototype",
		HostingSystem: vm, SchemaVersion: schemaversion.SchemaV21(), Spec: containerSpec(paths), WCOWLayers: wl, DoNotReleaseResourcesOnFailure: true})
	if err != nil {
		return err
	}
	if err = container.Start(ctx); err != nil {
		return err
	}
	r.Stage = "bootstrap_runtimes"
	bundle, err := os.Open(filepath.Join(root, "runtime.zip"))
	if err != nil {
		return err
	}
	defer bundle.Close()
	bootstrap := `$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';$w='` + workspace + `';[IO.Directory]::CreateDirectory($w)|Out-Null;$f=[IO.File]::Create($w+'\runtime.zip');try{[Console]::OpenStandardInput().CopyTo($f)}finally{$f.Dispose()};Expand-Archive -LiteralPath ($w+'\runtime.zip') -DestinationPath $w;[Console]::WriteLine('CTM_BOOTSTRAP_ENTRY');exit 23`
	run := func(name, command, cwd, marker string, input io.Reader) error {
		c, stop := context.WithTimeout(ctx, 60*time.Second)
		defer stop()
		result, e := runGuest(c, container, name, command, cwd, marker, input)
		r.Cases = append(r.Cases, result)
		return e
	}
	if err = run("bootstrap", encodedCommand(bootstrap), `C:\`, "CTM_BOOTSTRAP_ENTRY", bundle); err != nil {
		return err
	}
	for _, c := range runtimeCommands() {
		r.Stage = "runtime_" + c.name
		if err = run(c.name, c.command, workspace, c.marker, nil); err != nil {
			return err
		}
	}
	r.Stage = "live_descendant"
	if err = run("parent", `"`+workspace+`\fixture.exe" parent`, workspace, "CTM_PARENT_ENTRY", nil); err != nil {
		return err
	}
	if err = run("child-live", `"`+workspace+`\fixture.exe" check`, workspace, "CTM_CHILD_LIVE", nil); err != nil {
		return err
	}
	stillRunning, cancelCheck := context.WithTimeout(ctx, 100*time.Millisecond)
	defer cancelCheck()
	if e := vm.WaitCtx(stillRunning); !errors.Is(e, context.DeadlineExceeded) {
		return fmt.Errorf("UVM unexpectedly exited before termination: %v", e)
	}
	r.RuntimePassed = true
	r.Stage = "terminate_owned_uvm"
	return nil
}
func main() {
	root := os.Getenv("CTM_BOOT_ROOT")
	evidence := os.Getenv("CTM_BOOT_EVIDENCE")
	if len(os.Args) != 2 || (os.Args[1] != "import" && os.Args[1] != "run") || root == "" || evidence == "" {
		fmt.Fprintln(os.Stderr, "fixed import/run mode and private paths required")
		os.Exit(2)
	}
	if os.Args[1] == "import" {
		err := importLayers(root)
		message := ""
		if err != nil {
			message = err.Error()
		}
		err = errors.Join(err, writeReport(filepath.Join(evidence, "import.json"), map[string]any{"error": message, "process_privileges_scoped": true, "image_layers": 2}))
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		return
	}
	r := report{Schema: 1, Source: os.Getenv("GITHUB_SHA"), Stage: "prepare", DataRetained: true}
	r.record("experiment", runPrototype(root, &r))
	if err := writeReport(filepath.Join(evidence, "result.json"), r); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if !complete(r) {
		fmt.Fprintln(os.Stderr, "prototype incomplete; inspect bounded result.json")
		os.Exit(1)
	}
}
