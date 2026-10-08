//go:build windows && !fixture

package main

import (
	"bytes"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"unicode/utf16"
)

func TestFixedVMOptions(t *testing.T) {
	o := buildOptions("synthetic-id")
	if o.ID != "synthetic-id" || o.ProcessorCount != 2 || o.MemorySizeInMB != 2048 || !o.NoWritableFileShares || !o.NoDirectMap || o.DisableCompartmentNamespace {
		t.Fatal("unexpected isolation defaults")
	}
	if o.NetworkConfigProxy != "" || o.ProcessDumpLocation != "" || o.DumpDirectoryPath != "" || o.CPUGroupID != "" || len(o.AdditionalHyperVConfig) != 0 || len(o.AdditionalRegistryKeys) != 0 {
		t.Fatal("optional host surface configured")
	}
}
func TestContainerHasNoOptionalHostSurface(t *testing.T) {
	s := containerSpec([]string{"top", "base", "scratch"})
	if s.Windows.Network != nil || len(s.Windows.Devices) != 0 || s.Windows.CredentialSpec != nil || s.Windows.HyperV != nil || len(s.Mounts) != 0 || len(s.Annotations) != 0 || s.Linux != nil {
		t.Fatal("unexpected container surface")
	}
	if len(s.Windows.LayerFolders) != 3 {
		t.Fatal("layer inventory")
	}
}
func TestPinnedLayerInventory(t *testing.T) {
	if len(imageLayers) != 2 || imageLayers[0].size+imageLayers[1].size != 2396769443 {
		t.Fatal("image pin changed")
	}
	for _, l := range imageLayers {
		if len(l.digest) != 64 || l.size <= 0 {
			t.Fatal("invalid immutable descriptor")
		}
	}
}
func TestEncodedPowerShellRoundtrip(t *testing.T) {
	want := "Write-Output 'bounded Ω'"
	command := encodedCommand(want)
	part := strings.Split(command, " -EncodedCommand ")
	if len(part) != 2 || !strings.Contains(part[0], "-NoProfile -NonInteractive") {
		t.Fatal("fixed command flags")
	}
	b, e := base64.StdEncoding.DecodeString(part[1])
	if e != nil {
		t.Fatal(e)
	}
	u := make([]uint16, len(b)/2)
	for i := range u {
		u[i] = binary.LittleEndian.Uint16(b[2*i:])
	}
	if string(utf16.Decode(u)) != want {
		t.Fatal("encoding changed")
	}
}
func TestRuntimeInventory(t *testing.T) {
	cs := runtimeCommands()
	if len(cs) != 4 {
		t.Fatal("four stock runtimes required")
	}
	for i, want := range []string{"cmd", "windows-powershell", "node", "pwsh"} {
		if cs[i].name != want || cs[i].marker == "" || cs[i].command == "" {
			t.Fatal("runtime case missing")
		}
		for _, bad := range []string{"http://", "https://", "ExecutionPolicy", "ContainerAdministrator"} {
			if strings.Contains(cs[i].command, bad) {
				t.Fatal("unexpected runtime authority")
			}
		}
	}
}
func TestOutputBound(t *testing.T) {
	var b boundedOutput
	input := bytes.Repeat([]byte("x"), outputLimit+99)
	n, e := b.Write(input)
	if e != nil || n != len(input) || b.Len() != outputLimit || !b.overflow {
		t.Fatal("bounded drain failed")
	}
	if n, e = b.Write([]byte("more")); n != 4 || e != nil || b.Len() != outputLimit {
		t.Fatal("continued drain failed")
	}
}
func TestCompletionRejectsEveryUncertainComponent(t *testing.T) {
	good := report{RuntimePassed: true, TerminateOK: true, WholeVMExited: true, ExitOK: true, CloseOK: true}
	if !complete(good) {
		t.Fatal("synthetic complete case")
	}
	for _, mutate := range []func(*report){
		func(r *report) { r.RuntimePassed = false }, func(r *report) { r.TerminateOK = false },
		func(r *report) { r.WholeVMExited = false }, func(r *report) { r.ExitOK = false }, func(r *report) { r.CloseOK = false },
		func(r *report) { r.Errors = []string{"earlier uncertainty"} },
	} {
		r := good
		mutate(&r)
		if complete(r) {
			t.Fatal("uncertainty erased")
		}
	}
}
func TestProductionFlagsRemainFalse(t *testing.T) {
	r := report{RuntimePassed: true, TerminateOK: true, WholeVMExited: true, ExitOK: true, CloseOK: true}
	b, e := json.Marshal(r)
	if e != nil {
		t.Fatal(e)
	}
	for _, key := range []string{"network_denial_proven", "workspace_integration", "production_admission"} {
		if !strings.Contains(string(b), `"`+key+`":false`) {
			t.Fatal("production claim escaped prototype")
		}
	}
}
func TestHashAndSizeRejectWrongInputs(t *testing.T) {
	d := t.TempDir()
	p := filepath.Join(d, "synthetic")
	if e := os.WriteFile(p, []byte("abc"), 0600); e != nil {
		t.Fatal(e)
	}
	h := "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
	if e := verifyFile(p, h, 3); e != nil {
		t.Fatal(e)
	}
	if verifyFile(p, h, 4) == nil || verifyFile(p, strings.Repeat("0", 64), 3) == nil {
		t.Fatal("mismatch accepted")
	}
}
