//go:build windows && !fixture && go1.24

package main

import (
	"bytes"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func makeSurfaceTest(t *testing.T) (*surfaceFixture, string) {
	t.Helper()
	root := t.TempDir()
	f, e := newSurfaceFixture(root)
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(func() {
		if e := f.close(); e != nil {
			t.Error(e)
		}
	})
	return f, root
}
func syntheticSurfaceReply(f *surfaceFixture) transferReply {
	b := bytes.ToUpper(f.packet.Data)
	r := transferReply{Marker: "CTM_SURFACE_ENTRY", Nonce: f.packet.Nonce, InputSHA: f.packet.InputSHA, Data: b, OutputSHA: fixtureHash(b)}
	for _, s := range socketInventory {
		r.Allocations = append(r.Allocations, socketObservation{Name: s.name, Error: "synthetic-not-executed"})
	}
	for _, s := range []string{"tcp4", "tcp6", "unix"} {
		r.Peers = append(r.Peers, socketObservation{Name: s, Error: "synthetic-not-executed"})
	}
	return r
}
func completedSurfaceTest() report {
	return report{RuntimePassed: true, TerminateOK: true, WholeVMExited: true, ExitOK: true, CloseOK: true}
}
func requireQuarantineAbsent(t *testing.T, f *surfaceFixture) {
	t.Helper()
	p, e := f.quarantine.Open("returned.bin")
	if e == nil {
		p.Close()
		t.Fatal("quarantine unexpectedly written")
	}
	if !os.IsNotExist(e) || f.receipt.QuarantineWritten {
		t.Fatalf("unexpected quarantine state: %v", e)
	}
}
func TestSurfaceInventoryIsFixed(t *testing.T) {
	if len(socketInventory) != 6 {
		t.Fatal("allocation inventory changed")
	}
	for i, s := range socketInventory {
		if s.name != []string{"ipv4-tcp", "ipv4-udp", "ipv6-tcp", "ipv6-udp", "unix-stream", "hyperv-allocation-only"}[i] {
			t.Fatal("surface changed")
		}
	}
	if socketInventory[5].family != 34 || socketInventory[5].protocol != 1 {
		t.Fatal("AF_HYPERV allocation tuple changed")
	}
}
func TestSurfaceRootRenameAndEscape(t *testing.T) {
	f, root := makeSurfaceTest(t)
	if e := os.WriteFile(filepath.Join(root, "sentinel"), []byte("synthetic-outside-source"), 0600); e != nil {
		t.Fatal(e)
	}
	if p, e := f.source.Open("../sentinel"); e == nil {
		p.Close()
		t.Fatal("fixture root escape")
	}
	if e := os.Rename(filepath.Join(root, "surface-source"), filepath.Join(root, "moved")); e == nil {
		t.Fatal("Windows Root did not prevent rename")
	}
	if id, e := fixtureIdentity(f.directory, true); e != nil || id != f.receipt.SourceDirectory {
		t.Fatal("held directory identity changed")
	}
	requireQuarantineAbsent(t, f)
}
func TestSurfaceEnvelopeBoundsAndCorrelation(t *testing.T) {
	f, _ := makeSurfaceTest(t)
	for _, mutate := range []func(*transferReply){
		func(r *transferReply) { r.Nonce = "foreign" }, func(r *transferReply) { r.InputSHA = "foreign" },
		func(r *transferReply) { r.OutputSHA = "foreign" }, func(r *transferReply) { r.Data = make([]byte, 1025) },
		func(r *transferReply) { r.Allocations = r.Allocations[:5] }, func(r *transferReply) { r.Peers[0].CloseError = "uncertain" },
	} {
		r := syntheticSurfaceReply(f)
		mutate(&r)
		b, _ := json.Marshal(r)
		if f.accept(string(b)) == nil {
			t.Fatal("invalid envelope accepted")
		}
		requireQuarantineAbsent(t, f)
	}
	for _, b := range []string{strings.Repeat("x", 8193), `{} {}`, `{"unknown":1}`} {
		if f.accept(b) == nil {
			t.Fatal("malformed envelope accepted")
		}
	}
}
func TestSurfaceIncompleteLifetimeCannotWrite(t *testing.T) {
	f, _ := makeSurfaceTest(t)
	b, _ := json.Marshal(syntheticSurfaceReply(f))
	if e := f.accept(string(b)); e != nil {
		t.Fatal(e)
	}
	r := completedSurfaceTest()
	r.WholeVMExited = false
	if f.finishQuarantine(r) == nil {
		t.Fatal("unconfirmed VM exit accepted")
	}
	requireQuarantineAbsent(t, f)
	r = completedSurfaceTest()
	r.Errors = []string{"earlier uncertainty"}
	if f.finishQuarantine(r) == nil {
		t.Fatal("uncertainty erased")
	}
	requireQuarantineAbsent(t, f)
}
func TestSurfaceSourceMutationCannotWrite(t *testing.T) {
	f, _ := makeSurfaceTest(t)
	b, _ := json.Marshal(syntheticSurfaceReply(f))
	if e := f.accept(string(b)); e != nil {
		t.Fatal(e)
	}
	w, e := f.source.OpenFile("input.bin", os.O_WRONLY|os.O_TRUNC, 0600)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = w.Write([]byte("changed")); e != nil {
		t.Fatal(e)
	}
	if e = w.Close(); e != nil {
		t.Fatal(e)
	}
	if f.finishQuarantine(completedSurfaceTest()) == nil {
		t.Fatal("changed source accepted")
	}
	requireQuarantineAbsent(t, f)
}
func TestSurfaceQuarantineExactBytesAndNoOverwrite(t *testing.T) {
	f, _ := makeSurfaceTest(t)
	b, _ := json.Marshal(syntheticSurfaceReply(f))
	if e := f.accept(string(b)); e != nil {
		t.Fatal(e)
	}
	if e := f.finishQuarantine(completedSurfaceTest()); e != nil {
		t.Fatal(e)
	}
	p, e := f.quarantine.Open("returned.bin")
	if e != nil {
		t.Fatal(e)
	}
	out, e := io.ReadAll(p)
	p.Close()
	if e != nil || !bytes.Equal(out, bytes.ToUpper(f.packet.Data)) || !f.receipt.QuarantineWritten || fixtureHash(out) != f.receipt.QuarantineSHA {
		t.Fatal("quarantine bytes mismatch")
	}
	if f.finishQuarantine(completedSurfaceTest()) == nil {
		t.Fatal("quarantine replay overwritten")
	}
}
