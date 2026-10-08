//go:build windows && !fixture

package main

import (
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

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

var imageLayers = []struct {
	digest string
	size   int64
}{
	{"97e96e9cbeb16024139f78dc6ed542a7cf572ac80d8cea50a3308368094c4574", 1482371926},
	{"67f39c55a3f42bc0569099cebb32cef6688837ca694dfacaa00053810cb810d6", 914397517},
}

type report struct {
	Schema              int             `json:"schema"`
	Source              string          `json:"source"`
	ID                  string          `json:"owned_uvm_id"`
	RuntimeID           string          `json:"runtime_id"`
	Stage               string          `json:"stage"`
	Cases               []caseResult    `json:"cases"`
	Errors              []string        `json:"errors"`
	TerminateOK         bool            `json:"terminate_ok"`
	WholeVMExited       bool            `json:"whole_vm_exited"`
	ExitOK              bool            `json:"exit_reason_ok"`
	CloseOK             bool            `json:"close_ok"`
	RuntimePassed       bool            `json:"runtime_passed"`
	NetworkDenied       bool            `json:"network_denial_proven"`
	WorkspaceIntegrated bool            `json:"workspace_integration"`
	ProductionAdmission bool            `json:"production_admission"`
	DataRetained        bool            `json:"owned_data_retained"`
	Surface             *surfaceReceipt `json:"synthetic_surface"`
	Policy              *policyResult   `json:"hvsocket_policy"`
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
func runPrototype(root string, r *report, ids []guid.GUID, control bool) (err error) {
	ctx, cancel := context.WithTimeout(context.Background(), 6*time.Minute)
	defer cancel()
	g, err := guid.NewV4()
	if err != nil {
		return err
	}
	r.ID = g.String()
	profile := "restricted"
	if control {
		profile = "control"
	}
	paths := []string{filepath.Join(root, "layer1"), filepath.Join(root, "layer0"), filepath.Join(root, "scratch-"+profile)}
	if err = os.Mkdir(paths[2], 0700); err != nil {
		return err
	}
	o := buildOptions(r.ID)
	policy, err := configurePolicy(o, ids, control)
	if err != nil {
		return err
	}
	r.Policy = policy.result
	defer func() { r.record("owned_endpoint_cleanup", policy.close()) }()
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
	r.Stage = "hvsocket_policy"
	if err = policy.run(ctx, vm, container, r); err != nil {
		return err
	}
	stillRunning, cancelCheck := context.WithTimeout(ctx, 100*time.Millisecond)
	defer cancelCheck()
	if e := vm.WaitCtx(stillRunning); !errors.Is(e, context.DeadlineExceeded) {
		return fmt.Errorf("UVM unexpectedly exited before termination: %v", e)
	}
	r.Stage = "terminate_owned_uvm"
	return nil
}

type staticResult struct {
	Schema              int                  `json:"schema"`
	Source              string               `json:"source"`
	Registrations       []*ownedRegistration `json:"registrations"`
	Profiles            []report             `json:"profiles"`
	Errors              []string             `json:"errors"`
	Passed              bool                 `json:"bounded_static_matrix_passed"`
	NetworkDenied       bool                 `json:"network_denial_proven"`
	WorkspaceIntegrated bool                 `json:"workspace_integration"`
	ProductionAdmission bool                 `json:"production_admission"`
}

func staticProfileComplete(r report) bool {
	if !r.TerminateOK || !r.WholeVMExited || !r.ExitOK || !r.CloseOK || len(r.Errors) != 0 || r.Policy == nil {
		return false
	}
	p := r.Policy
	if !p.MatrixPassed || !p.SessionExited || !p.CleanupOK {
		return false
	}
	return p.Profile == "control" || (p.Profile == "restricted" && r.RuntimePassed)
}
func runStaticSuite(root string) (s *staticResult) {
	s = &staticResult{Schema: 2, Source: os.Getenv("GITHUB_SHA")}
	own, e := newStaticRegistry()
	if own != nil {
		s.Registrations = own.items
	}
	defer func() {
		certain := true
		for _, r := range s.Profiles {
			if !r.TerminateOK || !r.WholeVMExited || !r.ExitOK || !r.CloseOK {
				certain = false
			}
		}
		if e := own.close(certain); e != nil {
			s.Errors = append(s.Errors, "registration cleanup: "+e.Error())
		}
		s.Passed = len(s.Profiles) == 2 && len(s.Errors) == 0
		for _, r := range s.Profiles {
			s.Passed = s.Passed && staticProfileComplete(r)
		}
		for _, k := range s.Registrations {
			s.Passed = s.Passed && k.Created && k.Verified && k.Deleted && !k.Retained
		}
		s.Passed = s.Passed && len(s.Registrations) == 2
	}()
	if e != nil {
		s.Errors = append(s.Errors, "registration setup: "+e.Error())
		return
	}
	for _, control := range []bool{true, false} {
		r := report{Schema: 2, Source: s.Source, Stage: "prepare", DataRetained: true}
		r.record("experiment", runPrototype(root, &r, own.ids, control))
		s.Profiles = append(s.Profiles, r)
		if !staticProfileComplete(r) {
			s.Errors = append(s.Errors, "profile incomplete; next VM forbidden")
			return
		}
	}
	return
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
	r := runStaticSuite(root)
	if err := writeReport(filepath.Join(evidence, "result.json"), r); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if !r.Passed {
		fmt.Fprintln(os.Stderr, "prototype incomplete; inspect bounded result.json")
		os.Exit(1)
	}
}
