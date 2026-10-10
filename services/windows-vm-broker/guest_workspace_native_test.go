//go:build windows

package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"os"
	"path/filepath"
	"syscall"
	"testing"
)

func guestNativeParent(t *testing.T) (*os.File, guestFileIdentity, string) {
	t.Helper()
	if os.Getenv("CTM_GUEST_FILE_NATIVE_ENABLE") != "OWNED_TEMP_FIXTURE_ONLY" {
		t.Fatal("native guest file proof requires approved temporary runner fixture")
	}
	base := os.Getenv("CTM_GUEST_FILE_NATIVE_ROOT")
	if base == "" || !filepath.IsAbs(base) {
		t.Fatal("absolute owned runner temp root required")
	}
	root, e := os.MkdirTemp(base, "ctm-guest-file-")
	if e != nil {
		t.Fatal(e)
	}
	wide, e := syscall.UTF16PtrFromString(root)
	if e != nil {
		t.Fatal(e)
	}
	handle, e := syscall.CreateFile(wide, 0x00100081, syscall.FILE_SHARE_READ|syscall.FILE_SHARE_WRITE, nil, syscall.OPEN_EXISTING, syscall.FILE_FLAG_BACKUP_SEMANTICS|syscall.FILE_FLAG_OPEN_REPARSE_POINT, 0)
	if e != nil {
		t.Fatal(e)
	}
	parent := os.NewFile(uintptr(handle), root)
	id, e := guestParentIdentity(parent)
	if e != nil {
		t.Fatal(e)
	}
	t.Cleanup(func() { _ = parent.Close(); _ = os.RemoveAll(root) })
	return parent, id, root
}
func guestNativeWire(data []byte) (workspaceStreamManifest, []byte) {
	m := streamManifest(data)
	w, _ := workspaceEncode(m, data)
	return m, w
}
func TestGuestNativeInputChunksActualFullFIDAndCheckedClose(t *testing.T) {
	parent, id, root := guestNativeParent(t)
	data := bytes.Repeat([]byte{3}, workspaceChunk+1)
	m, wire := guestNativeWire(data)
	f, evidence, e := receiveGuestWorkspaceInput(context.Background(), parent, id, "input.bin", m, bytes.NewReader(wire))
	if e != nil {
		t.Fatal(e)
	}
	if evidence.identity.id == ([16]byte{}) || evidence.identity.volume != id.volume || evidence.parent != id || evidence.binding != m.binding || evidence.digest != sha256.Sum256(data) {
		t.Fatal("actual held identity/hash evidence")
	}
	if _, e = os.OpenFile(filepath.Join(root, "input.bin"), os.O_WRONLY, 0); e == nil {
		t.Fatal("external writer accepted")
	}
	if e = f.closeKnown(); e != nil {
		t.Fatal(e)
	}
	if e = f.closeKnown(); e != nil {
		t.Fatal(e)
	}
	got, e := os.ReadFile(filepath.Join(root, "input.bin"))
	if e != nil || !bytes.Equal(got, data) {
		t.Fatal("after checked close")
	}
}
func TestGuestNativeCreateOnlyExistingInputNeverOverwrites(t *testing.T) {
	parent, id, root := guestNativeParent(t)
	p := filepath.Join(root, "input.bin")
	if e := os.WriteFile(p, []byte("existing"), 0600); e != nil {
		t.Fatal(e)
	}
	m, wire := guestNativeWire([]byte("replacement"))
	f, _, e := receiveGuestWorkspaceInput(context.Background(), parent, id, "input.bin", m, bytes.NewReader(wire))
	if e == nil {
		t.Fatal("replaced")
	}
	if f != nil {
		_ = f.closeKnown()
	}
	got, _ := os.ReadFile(p)
	if string(got) != "existing" {
		t.Fatal("existing modified")
	}
}
func TestGuestNativeWrongParentFullIDRejectsBeforeCreate(t *testing.T) {
	parent, id, root := guestNativeParent(t)
	id.id[15] ^= 1
	m, wire := guestNativeWire([]byte("canary"))
	f, _, e := receiveGuestWorkspaceInput(context.Background(), parent, id, "input.bin", m, bytes.NewReader(wire))
	if e == nil {
		t.Fatal("parent conflict")
	}
	if f != nil {
		_ = f.closeKnown()
	}
	if _, e = os.Stat(filepath.Join(root, "input.bin")); !os.IsNotExist(e) {
		t.Fatal("created before exact parent validation")
	}
}
func TestGuestNativeCancellationAndMalformedStreamNeverProduceEvidence(t *testing.T) {
	parent, id, _ := guestNativeParent(t)
	m, wire := guestNativeWire([]byte("canary"))
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	f, evidence, e := receiveGuestWorkspaceInput(ctx, parent, id, "input.bin", m, bytes.NewReader(wire))
	if e == nil || evidence.identity.id != ([16]byte{}) {
		t.Fatal("cancel evidence")
	}
	if f != nil {
		_ = f.closeKnown()
	}
	wire[len(wire)-1] ^= 1
	f, evidence, e = receiveGuestWorkspaceInput(context.Background(), parent, id, "input.bin", m, bytes.NewReader(wire))
	if e == nil || evidence.identity.id != ([16]byte{}) {
		t.Fatal("malformed evidence")
	}
	if f == nil || !f.createMayHaveEffect {
		t.Fatal("must describe possible guest create effect")
	}
	if e = f.closeKnown(); e != nil {
		t.Fatal(e)
	}
}
func TestGuestNativeActualCursorTamperPoisonsReadback(t *testing.T) {
	parent, id, _ := guestNativeParent(t)
	m, wire := guestNativeWire([]byte("canary"))
	f, _, e := receiveGuestWorkspaceInput(context.Background(), parent, id, "input.bin", m, bytes.NewReader(wire))
	if e != nil {
		t.Fatal(e)
	}
	if _, e = syscall.Seek(f.handle, 0, 0); e != nil {
		t.Fatal(e)
	}
	if _, e = f.observeInput([]byte("canary")); e == nil {
		t.Fatal("cursor tamper")
	}
	if e = f.closeKnown(); e != nil {
		t.Fatal(e)
	}
}
func TestGuestNativeControlledUnknownCloseKeepsRawHandleParentAndImmutableBytes(t *testing.T) {
	parent, id, root := guestNativeParent(t)
	m, wire := guestNativeWire([]byte("canary"))
	f, _, e := receiveGuestWorkspaceInput(context.Background(), parent, id, "input.bin", m, bytes.NewReader(wire))
	if e != nil {
		t.Fatal(e)
	}
	f.uncertain = true
	if e = f.closeKnown(); e == nil {
		t.Fatal("unknown close accepted")
	}
	if f.handle == 0 || f.parentHandle == 0 || !bytes.Equal(f.immutable, []byte("canary")) {
		t.Fatal("whole file evidence ownership lost")
	}
	guestHeld.Lock()
	held := guestHeld.entries[f]
	guestHeld.Unlock()
	if !held {
		t.Fatal("native owner not retained")
	}
	if _, e = os.OpenFile(filepath.Join(root, "input.bin"), os.O_WRONLY, 0); e == nil {
		t.Fatal("unknown handle not retained")
	}
}
func TestGuestNativeClosingCallerParentLeavesActualOwnedDuplicateLive(t *testing.T) {
	parent, id, _ := guestNativeParent(t)
	m, wire := guestNativeWire([]byte("canary"))
	f, _, e := receiveGuestWorkspaceInput(context.Background(), parent, id, "input.bin", m, bytes.NewReader(wire))
	if e != nil {
		t.Fatal(e)
	}
	if e = parent.Close(); e != nil {
		t.Fatal(e)
	}
	if e = f.check(); e != nil {
		t.Fatal("caller parent was borrowed rather than independently retained", e)
	}
	if _, e = f.observeInput([]byte("canary")); e != nil {
		t.Fatal(e)
	}
	if e = f.closeKnown(); e != nil {
		t.Fatal(e)
	}
}
