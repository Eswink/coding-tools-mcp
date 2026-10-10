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

func guestOutputFixture(t *testing.T, ctx context.Context) (*guestOwnedOutput, *guestOwnedFile, string) {
	t.Helper()
	parent, id, root := guestNativeParent(t)
	m, wire := guestNativeWire([]byte("input canary"))
	input, _, e := receiveGuestWorkspaceInput(context.Background(), parent, id, "input.bin", m, bytes.NewReader(wire))
	if e != nil {
		t.Fatal(e)
	}
	output, e := createGuestWorkspaceOutput(ctx, parent, id, "output.bin", input)
	if e != nil {
		t.Fatal(e)
	}
	return output, input, root
}
func guestWriteCommandFixture(t *testing.T, path string, data []byte) *os.File {
	t.Helper()
	w, e := os.OpenFile(path, os.O_WRONLY, 0)
	if e != nil {
		t.Fatal(e)
	}
	if n, e := w.Write(data); e != nil || n != len(data) {
		t.Fatal("fixture command write", e)
	}
	if e = w.Sync(); e != nil {
		t.Fatal(e)
	}
	return w
}
func TestGuestNativeOutputFullFIDHashDirectionAndCheckedAllClose(t *testing.T) {
	f, input, root := guestOutputFixture(t, context.Background())
	data := bytes.Repeat([]byte{17}, workspaceChunk+1)
	w := guestWriteCommandFixture(t, filepath.Join(root, "output.bin"), data)
	if e := w.Close(); e != nil {
		t.Fatal(e)
	}
	evidence, e := f.freeze()
	if e != nil || evidence.input.identity != input.identity || evidence.input.digest != input.manifest.digest || evidence.output.identity != f.identity || evidence.output.parent != f.parentID || evidence.output.size != uint64(len(data)) || evidence.output.digest != sha256.Sum256(data) {
		t.Fatal("actual input/output FID/hash evidence", e)
	}
	if w, e := os.OpenFile(filepath.Join(root, "output.bin"), os.O_WRONLY, 0); e == nil {
		_ = w.Close()
		t.Fatal("new writer accepted after strict reopen")
	}
	_, wire, e := f.wire()
	if e != nil {
		t.Fatal(e)
	}
	m := workspaceStreamManifest{binding: evidence.output.binding, direction: 2, total: evidence.output.size, digest: evidence.output.digest}
	s, e := newWorkspaceStream(context.Background(), m)
	if e != nil || s.readAll(bytes.NewReader(wire), nil) != nil {
		t.Fatal("actual output stream", e)
	}
	got, e := s.dataCopy()
	if e != nil || !bytes.Equal(got, data) {
		t.Fatal("actual immutable output bytes", e)
	}
	if _, _, e = f.wire(); e == nil {
		t.Fatal("output replay accepted")
	}
	if e = f.closeKnown(); e != nil || f.parentDuplicate != 0 || f.parentPin != 0 || f.pin != 0 || f.read != 0 || f.writer != 0 || f.immutable != nil {
		t.Fatal("not all actual output handles checked closed", e)
	}
	guestOutputHeld.Lock()
	held := guestOutputHeld.entries[f]
	guestOutputHeld.Unlock()
	if held {
		t.Fatal("checked-closed output owner still registered")
	}
	if e = input.closeKnown(); e != nil {
		t.Fatal(e)
	}
}
func TestGuestNativeOutputExistingTargetNeverReplaces(t *testing.T) {
	parent, id, root := guestNativeParent(t)
	m, wire := guestNativeWire([]byte("input"))
	input, _, e := receiveGuestWorkspaceInput(context.Background(), parent, id, "input.bin", m, bytes.NewReader(wire))
	if e != nil {
		t.Fatal(e)
	}
	p := filepath.Join(root, "output.bin")
	if e = os.WriteFile(p, []byte("existing canary"), 0600); e != nil {
		t.Fatal(e)
	}
	f, e := createGuestWorkspaceOutput(context.Background(), parent, id, "output.bin", input)
	if e == nil {
		t.Fatal("existing output accepted")
	}
	if e = f.closeKnown(); e != nil {
		t.Fatal(e)
	}
	got, e := os.ReadFile(p)
	if e != nil || string(got) != "existing canary" {
		t.Fatal("existing output modified", e)
	}
	if e = input.closeKnown(); e != nil {
		t.Fatal(e)
	}
}
func TestGuestNativeOutputSurvivingWriterRejectsStrictFreeze(t *testing.T) {
	f, input, root := guestOutputFixture(t, context.Background())
	w := guestWriteCommandFixture(t, filepath.Join(root, "output.bin"), []byte("writer canary"))
	if evidence, e := f.freeze(); e == nil || evidence.output.identity.id != ([16]byte{}) {
		t.Fatal("surviving writer accepted")
	}
	if !f.poisoned || f.pin == 0 || f.parentPin == 0 || !f.createMayHaveEffect {
		t.Fatal("surviving writer discarded raw owner/effect")
	}
	if e := w.Close(); e != nil {
		t.Fatal(e)
	}
	if _, e := f.freeze(); e == nil {
		t.Fatal("sticky rejected owner retried")
	}
	if e := f.closeKnown(); e != nil {
		t.Fatal(e)
	}
	if e := input.closeKnown(); e != nil {
		t.Fatal(e)
	}
}
func TestGuestNativeOutputActualParentPinAndTargetDenyRename(t *testing.T) {
	parent, id, root := guestNativeParent(t)
	if e := parent.Close(); e != nil {
		t.Fatal(e)
	}
	wide, _ := syscall.UTF16PtrFromString(root)
	h, e := syscall.CreateFile(wide, 0x00100081, 7, nil, syscall.OPEN_EXISTING, syscall.FILE_FLAG_BACKUP_SEMANTICS|syscall.FILE_FLAG_OPEN_REPARSE_POINT, 0)
	if e != nil {
		t.Fatal(e)
	}
	parent = os.NewFile(uintptr(h), root)
	m, wire := guestNativeWire([]byte("input"))
	input, _, e := receiveGuestWorkspaceInput(context.Background(), parent, id, "input.bin", m, bytes.NewReader(wire))
	if e != nil {
		t.Fatal(e)
	}
	f, e := createGuestWorkspaceOutput(context.Background(), parent, id, "output.bin", input)
	if e != nil {
		t.Fatal(e)
	}
	if e = parent.Close(); e != nil {
		t.Fatal(e)
	}
	// Caller and duplicated input parent allowed DELETE sharing. Only the actual
	// new parentPin denies rename of this directory object at this point.
	from, _ := syscall.UTF16PtrFromString(root)
	to, _ := syscall.UTF16PtrFromString(root + "-renamed")
	if e = syscall.MoveFile(from, to); e == nil {
		t.Fatal("actual parent pin allowed rename")
	}
	from, _ = syscall.UTF16PtrFromString(filepath.Join(root, "output.bin"))
	to, _ = syscall.UTF16PtrFromString(filepath.Join(root, "other.bin"))
	if e = syscall.MoveFile(from, to); e == nil {
		t.Fatal("actual output pin allowed replacement/rename")
	}
	if _, e = f.checkPin(); e != nil {
		t.Fatal(e)
	}
	if e = f.closeKnown(); e != nil {
		t.Fatal(e)
	}
	if e = input.closeKnown(); e != nil {
		t.Fatal(e)
	}
}
func TestGuestNativeOutputWrongInputFullIDRejectsBeforeCreate(t *testing.T) {
	parent, id, root := guestNativeParent(t)
	m, wire := guestNativeWire([]byte("input"))
	input, _, e := receiveGuestWorkspaceInput(context.Background(), parent, id, "input.bin", m, bytes.NewReader(wire))
	if e != nil {
		t.Fatal(e)
	}
	input.identity.id[15] ^= 1
	f, e := createGuestWorkspaceOutput(context.Background(), parent, id, "output.bin", input)
	if e == nil || f.createMayHaveEffect {
		t.Fatal("wrong actual input ID reached create")
	}
	if _, e = os.Stat(filepath.Join(root, "output.bin")); !os.IsNotExist(e) {
		t.Fatal("output created before actual input verification")
	}
	_ = f.closeKnown()
	if e = input.closeKnown(); e != nil {
		t.Fatal(e)
	}
}
func TestGuestNativeOutputBoundsAndActualCursorTamperRejectData(t *testing.T) {
	t.Run("oversized", func(t *testing.T) {
		f, input, root := guestOutputFixture(t, context.Background())
		w := guestWriteCommandFixture(t, filepath.Join(root, "output.bin"), bytes.Repeat([]byte{2}, workspaceMaximum+1))
		if e := w.Close(); e != nil {
			t.Fatal(e)
		}
		if _, e := f.freeze(); e == nil || f.immutable != nil {
			t.Fatal("oversized data allocated or accepted")
		}
		_ = f.closeKnown()
		_ = input.closeKnown()
	})
	t.Run("cursor", func(t *testing.T) {
		f, input, root := guestOutputFixture(t, context.Background())
		w := guestWriteCommandFixture(t, filepath.Join(root, "output.bin"), []byte("output"))
		if e := w.Close(); e != nil {
			t.Fatal(e)
		}
		if _, e := f.freeze(); e != nil {
			t.Fatal(e)
		}
		if _, e := syscall.Seek(f.read, 0, 0); e != nil {
			t.Fatal(e)
		}
		if _, wire, e := f.wire(); e == nil || wire != nil {
			t.Fatal("actual changed cursor accepted")
		}
		_ = f.closeKnown()
		_ = input.closeKnown()
	})
}
func TestGuestNativeOutputCancellationRejectsEvidenceAndPreservesEffect(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	f, input, _ := guestOutputFixture(t, ctx)
	cancel()
	if evidence, e := f.freeze(); e == nil || evidence.output.identity.id != ([16]byte{}) || !f.createMayHaveEffect || f.parentPin == 0 || f.pin == 0 {
		t.Fatal("cancel lost possible created effect/raw owner")
	}
	if e := f.closeKnown(); e != nil {
		t.Fatal(e)
	}
	if e := input.closeKnown(); e != nil {
		t.Fatal(e)
	}
}
func TestGuestNativeOutputActualFailedCloseRetainsPinsBytesAndRawValue(t *testing.T) {
	f, input, root := guestOutputFixture(t, context.Background())
	w := guestWriteCommandFixture(t, filepath.Join(root, "output.bin"), []byte("output canary"))
	if e := w.Close(); e != nil {
		t.Fatal(e)
	}
	if _, e := f.freeze(); e != nil {
		t.Fatal(e)
	}
	// Controlled fault: invalidate this field without opening any intervening
	// handle. Its next actual CloseHandle fails; never claim the stale value live.
	old := f.read
	if e := syscall.CloseHandle(old); e != nil {
		t.Fatal(e)
	}
	if e := f.closeKnown(); e == nil || !f.uncertain || f.read != old || f.pin == 0 || f.parentPin == 0 || !bytes.Equal(f.immutable, []byte("output canary")) {
		t.Fatal("failed actual close discarded whole diagnostic owner")
	}
	guestOutputHeld.Lock()
	held := guestOutputHeld.entries[f]
	guestOutputHeld.Unlock()
	if !held {
		t.Fatal("failed-close whole owner absent")
	}
	if info, e := guestRawInfo(f.pin); e != nil || info.identity != f.identity {
		t.Fatal("still-live original pin lost", e)
	}
	if _, _, e := f.wire(); e == nil {
		t.Fatal("unknown closure accepted data")
	}
	_ = input.closeKnown()
}
func TestGuestNativeOutputPanicRetainsRegistryAndRejectsData(t *testing.T) {
	f, input, root := guestOutputFixture(t, context.Background())
	w := guestWriteCommandFixture(t, filepath.Join(root, "output.bin"), []byte("panic canary"))
	if e := w.Close(); e != nil {
		t.Fatal(e)
	}
	if _, e := f.freeze(); e != nil {
		t.Fatal(e)
	}
	func() {
		defer func() {
			if recover() == nil {
				t.Fatal("controlled panic missing")
			}
		}()
		func() { defer f.markPanic(); panic("controlled owner unwind") }()
	}()
	guestOutputHeld.Lock()
	held := guestOutputHeld.entries[f]
	guestOutputHeld.Unlock()
	if !held || !f.poisoned || f.read == 0 || f.pin == 0 || f.parentPin == 0 || !bytes.Equal(f.immutable, []byte("panic canary")) {
		t.Fatal("panic discarded raw owner/bytes")
	}
	if _, _, e := f.wire(); e == nil {
		t.Fatal("panic owner accepted data")
	}
	if e := f.closeKnown(); e != nil {
		t.Fatal(e)
	}
	if e := input.closeKnown(); e != nil {
		t.Fatal(e)
	}
}
