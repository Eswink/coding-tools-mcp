//go:build windows

package main

// Independent ordinary Windows API controls. These fixtures are guest data,
// never a VM owner, RunBinding authority, publisher grant or allIO seal.
import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"sync"
	"syscall"
	"testing"
	"unsafe"
)

type guestOutputBoundaryOwned struct {
	root        string
	parent      *os.File
	id          guestFileIdentity
	input       *guestOwnedFile
	output      *guestOwnedOutput
	quarantined bool
	extra       []syscall.Handle
}

// Strongly retain uncertain fixtures until this exact test process exits. No
// os.File finalizer, cleanup retry or RemoveAll may retire these resources.
var guestOutputBoundaryQuarantine = struct {
	sync.Mutex
	entries map[*guestOutputBoundaryOwned]bool
}{entries: make(map[*guestOutputBoundaryOwned]bool)}

func guestOutputBoundaryFixture(t *testing.T) *guestOutputBoundaryOwned {
	t.Helper()
	if os.Getenv("CTM_GUEST_FILE_NATIVE_ENABLE") != "OWNED_TEMP_FIXTURE_ONLY" {
		t.Fatal("ordinary owned Windows fixture selection required; not authority")
	}
	base := os.Getenv("CTM_GUEST_FILE_NATIVE_ROOT")
	if !filepath.IsAbs(base) {
		t.Fatal("absolute fresh runner fixture root required")
	}
	root, err := os.MkdirTemp(base, "ctm-output-boundary-")
	if err != nil {
		t.Fatal(err)
	}
	f := &guestOutputBoundaryOwned{root: root}
	// Register before the first native parent acquisition so a later uncertain
	// result cannot lose the os.File or owned data through helper unwinding.
	guestOutputBoundaryQuarantine.Lock()
	guestOutputBoundaryQuarantine.entries[f] = true
	guestOutputBoundaryQuarantine.Unlock()
	t.Cleanup(func() { guestOutputBoundaryClose(t, f) })
	h, err := guestOutputBoundaryOpen(root, 0x00100081, 7, true)
	if err != nil {
		t.Fatal(err)
	}
	f.parent = os.NewFile(uintptr(h), root)
	f.id, err = guestParentIdentity(f.parent)
	if err != nil {
		t.Fatal(err)
	}
	m, wire := guestNativeWire([]byte("boundary input canary"))
	f.input, _, err = receiveGuestWorkspaceInput(context.Background(), f.parent, f.id, "input.bin", m, bytes.NewReader(wire))
	if err != nil {
		t.Fatal(err)
	}
	return f
}

func guestOutputBoundaryOpen(path string, access, share uint32, directory bool) (syscall.Handle, error) {
	wide, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		return 0, err
	}
	flags := uint32(syscall.FILE_FLAG_OPEN_REPARSE_POINT)
	if directory {
		flags |= syscall.FILE_FLAG_BACKUP_SEMANTICS
	}
	return syscall.CreateFile(wide, access, share, nil, syscall.OPEN_EXISTING, flags, 0)
}

func guestOutputBoundaryClose(t *testing.T, f *guestOutputBoundaryOwned) {
	t.Helper()
	if len(f.extra) != 0 {
		f.quarantined = true
	}
	if f.quarantined || (f.output != nil && f.output.uncertain) || (f.input != nil && f.input.uncertain) {
		f.quarantined = true
		return
	}
	if f.output != nil {
		if err := f.output.closeKnown(); err != nil {
			f.quarantined = true
			t.Error("output cleanup uncertain", err)
			return
		}
	}
	if f.input != nil {
		if err := f.input.closeKnown(); err != nil {
			f.quarantined = true
			t.Error("input cleanup uncertain", err)
			return
		}
	}
	if f.parent != nil {
		if err := f.parent.Close(); err != nil {
			f.quarantined = true
			t.Error("parent cleanup uncertain", err)
			return
		}
		f.parent = nil
	}
	if err := os.RemoveAll(f.root); err != nil {
		f.quarantined = true
		t.Error("known-closed fixture cleanup", err)
		return
	}
	guestOutputBoundaryQuarantine.Lock()
	delete(guestOutputBoundaryQuarantine.entries, f)
	guestOutputBoundaryQuarantine.Unlock()
}

func guestOutputBoundaryCreate(t *testing.T, f *guestOutputBoundaryOwned) {
	t.Helper()
	var err error
	f.output, err = createGuestWorkspaceOutput(context.Background(), f.parent, f.id, "output.bin", f.input)
	if err != nil {
		t.Fatal(err)
	}
}

func guestOutputBoundaryDeleteProbe(t *testing.T, f *guestOutputBoundaryOwned, rejected bool) {
	t.Helper()
	h, err := guestOutputBoundaryOpen(f.root, 0x00110080, 7, true)
	if rejected {
		if err == nil {
			f.extra = append(f.extra, h)
			if closeErr := syscall.CloseHandle(h); closeErr != nil {
				f.quarantined = true
				t.Fatal(closeErr)
			}
			f.extra = f.extra[:len(f.extra)-1]
			t.Fatal("actual DELETE access accepted while independent noDELETE parent pin exists")
		}
		if err != syscall.Errno(32) {
			t.Fatal("expected actual sharing violation, not arbitrary native failure", err)
		}
		return
	}
	if err != nil {
		t.Fatal("actual DELETE access capability unavailable", err)
	}
	f.extra = append(f.extra, h)
	info, infoErr := guestRawInfo(h)
	closeErr := syscall.CloseHandle(h)
	if closeErr != nil {
		f.quarantined = true
		t.Fatal("DELETE probe close uncertain", closeErr)
	}
	f.extra = f.extra[:len(f.extra)-1]
	if infoErr != nil || !info.directory || info.identity != f.id {
		t.Fatal("DELETE probe different actual parent object", infoErr)
	}
}

func guestOutputBoundaryReadInfo(t *testing.T, f *guestOutputBoundaryOwned, path string) guestFileInfo {
	t.Helper()
	h, err := guestOutputBoundaryOpen(path, 0x00100080, 7, false)
	if err != nil {
		t.Fatal(err)
	}
	f.extra = append(f.extra, h)
	info, infoErr := guestRawInfo(h)
	closeErr := syscall.CloseHandle(h)
	if closeErr != nil {
		f.quarantined = true
		t.Fatal("canary observation close failed", closeErr)
	}
	f.extra = f.extra[:len(f.extra)-1]
	if infoErr != nil {
		t.Fatal(infoErr)
	}
	return info
}

func guestOutputBoundaryCanary(t *testing.T, f *guestOutputBoundaryOwned, path string, want []byte, id guestFileIdentity) {
	t.Helper()
	actual := guestOutputBoundaryReadInfo(t, f, path)
	data, err := os.ReadFile(path)
	if err != nil || !bytes.Equal(data, want) || actual.identity != id {
		t.Fatal("actual canary bytes/full object identity changed", err)
	}
}

func guestOutputBoundaryFlags(t *testing.T, h syscall.Handle) uint32 {
	t.Helper()
	var flags uint32
	get := syscall.NewLazyDLL("kernel32.dll").NewProc("GetHandleInformation")
	ok, _, err := get.Call(uintptr(h), uintptr(unsafe.Pointer(&flags)))
	if ok == 0 {
		t.Fatal("actual GetHandleInformation failed", err)
	}
	return flags
}

func guestOutputBoundarySetFlags(t *testing.T, h syscall.Handle, mask, value uint32) {
	t.Helper()
	set := syscall.NewLazyDLL("kernel32.dll").NewProc("SetHandleInformation")
	ok, _, err := set.Call(uintptr(h), uintptr(mask), uintptr(value))
	if ok == 0 {
		t.Fatal("actual SetHandleInformation failed", err)
	}
}

func guestOutputBoundaryAssertHeld(t *testing.T, f *guestOwnedOutput, want bool) {
	t.Helper()
	guestOutputHeld.Lock()
	actual := guestOutputHeld.entries[f]
	guestOutputHeld.Unlock()
	if actual != want {
		t.Fatal("actual strong output registry membership", actual, want)
	}
}

func TestGuestNativeOutputBoundaryParentPinExactSharing(t *testing.T) {
	f := guestOutputBoundaryFixture(t)
	// Caller and the actual input duplicate both share DELETE. Probe the same
	// complete directory identity before, during and after the output pin.
	guestOutputBoundaryDeleteProbe(t, f, false)
	guestOutputBoundaryCreate(t, f)
	for _, h := range []syscall.Handle{f.output.parentDuplicate, f.output.parentPin} {
		info, err := guestRawInfo(h)
		if err != nil || info.identity != f.id || !info.directory {
			t.Fatal("actual pinned parent identity", err)
		}
		if guestOutputBoundaryFlags(t, h)&1 != 0 {
			t.Fatal("native parent handle inherited")
		}
	}
	guestOutputBoundaryDeleteProbe(t, f, true)
	if err := f.output.closeKnown(); err != nil {
		t.Fatal(err)
	}
	guestOutputBoundaryAssertHeld(t, f.output, false)
	guestOutputBoundaryDeleteProbe(t, f, false)
}

func TestGuestNativeOutputBoundaryExclusiveHardlinkCanary(t *testing.T) {
	for _, hardlink := range []bool{false, true} {
		name := "regular"
		if hardlink {
			name = "genuine-hardlink"
		}
		t.Run(name, func(t *testing.T) {
			f := guestOutputBoundaryFixture(t)
			path := filepath.Join(f.root, "output.bin")
			alias := filepath.Join(f.root, "alias.bin")
			canary := []byte("exclusive creation leaves original canary unchanged")
			if err := os.WriteFile(path, canary, 0600); err != nil {
				t.Fatal(err)
			}
			if hardlink {
				if err := os.Link(path, alias); err != nil {
					t.Fatal("real hardlink capability unavailable", err)
				}
			}
			before := guestOutputBoundaryReadInfo(t, f, path)
			if before.identity.volume != f.id.volume || before.directory {
				t.Fatal("actual existing object/volume invalid")
			}
			if hardlink {
				other := guestOutputBoundaryReadInfo(t, f, alias)
				if before.links != 2 || other.links != 2 || other.identity != before.identity {
					t.Fatal("not an actual two-link same object")
				}
			}
			var err error
			f.output, err = createGuestWorkspaceOutput(context.Background(), f.parent, f.id, "output.bin", f.input)
			if err == nil {
				t.Fatal("FILE_CREATE replaced an existing native target")
			}
			if closeErr := f.output.closeKnown(); closeErr != nil {
				t.Fatal(closeErr)
			}
			guestOutputBoundaryCanary(t, f, path, canary, before.identity)
			if hardlink {
				guestOutputBoundaryCanary(t, f, alias, canary, before.identity)
			}
			// This collision control does not claim the links>1 checkPin branch.
		})
	}
}

func TestGuestNativeOutputBoundaryReparseCanary(t *testing.T) {
	f := guestOutputBoundaryFixture(t)
	path := filepath.Join(f.root, "output.bin")
	target := filepath.Join(f.root, "canary.bin")
	canary := []byte("owned genuine reparse destination canary")
	if err := os.WriteFile(target, canary, 0600); err != nil {
		t.Fatal(err)
	}
	before := guestOutputBoundaryReadInfo(t, f, target)
	if err := os.Symlink(target, path); err != nil {
		t.Fatal("real reparse fixture capability unavailable; no skip", err)
	}
	wide, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		t.Fatal(err)
	}
	attrs, err := syscall.GetFileAttributes(wide)
	if err != nil || attrs&syscall.FILE_ATTRIBUTE_REPARSE_POINT == 0 {
		t.Fatal("fixture is not actual reparse object", err)
	}
	h, err := guestOutputBoundaryOpen(path, 0x00100080, 7, false)
	if err != nil {
		t.Fatal(err)
	}
	f.extra = append(f.extra, h)
	_, rejected := guestRawInfo(h)
	closeErr := syscall.CloseHandle(h)
	if closeErr != nil {
		f.quarantined = true
		t.Fatal(closeErr)
	}
	f.extra = f.extra[:len(f.extra)-1]
	if rejected == nil {
		t.Fatal("actual reparse handle accepted as regular data")
	}
	f.output, err = createGuestWorkspaceOutput(context.Background(), f.parent, f.id, "output.bin", f.input)
	if err == nil {
		t.Fatal("actual reparse existing target accepted by FILE_CREATE")
	}
	if closeErr := f.output.closeKnown(); closeErr != nil {
		t.Fatal(closeErr)
	}
	guestOutputBoundaryCanary(t, f, target, canary, before.identity)
	// The create rejection may be collision, not a traced DONT_REPARSE status.
}

func TestGuestNativeOutputBoundaryKnownCloseCanary(t *testing.T) {
	f := guestOutputBoundaryFixture(t)
	guestOutputBoundaryCreate(t, f)
	path := filepath.Join(f.root, "output.bin")
	canary := []byte("known checked close output canary")
	w := guestWriteCommandFixture(t, path, canary)
	if err := w.Close(); err != nil {
		f.quarantined = true
		t.Fatal(err)
	}
	if _, err := f.output.freeze(); err != nil {
		t.Fatal(err)
	}
	id := f.output.identity
	if err := f.output.closeKnown(); err != nil {
		t.Fatal(err)
	}
	if !f.output.closed || f.output.uncertain || f.output.writer != 0 || f.output.read != 0 || f.output.pin != 0 || f.output.parentPin != 0 || f.output.parentDuplicate != 0 || f.output.immutable != nil {
		t.Fatal("not every actual output handle checked closed")
	}
	guestOutputBoundaryAssertHeld(t, f.output, false)
	guestOutputBoundaryDeleteProbe(t, f, false)
	renamed := filepath.Join(f.root, "closed-output.bin")
	if err := os.Rename(path, renamed); err != nil {
		t.Fatal("independent actual rename after checked close", err)
	}
	guestOutputBoundaryCanary(t, f, renamed, canary, id)
}

func TestGuestNativeOutputBoundaryFailedCloseQuarantine(t *testing.T) {
	f := guestOutputBoundaryFixture(t)
	guestOutputBoundaryCreate(t, f)
	path := filepath.Join(f.root, "output.bin")
	canary := []byte("protected close retains whole owner canary")
	w := guestWriteCommandFixture(t, path, canary)
	if err := w.Close(); err != nil {
		f.quarantined = true
		t.Fatal(err)
	}
	if _, err := f.output.freeze(); err != nil {
		t.Fatal(err)
	}
	raw := f.output.read
	// Real live-handle flag avoids invalidated-number reuse. Quarantine is sticky
	// before protection; neither a failure nor cleanup clears this native flag.
	f.quarantined = true
	guestOutputBoundarySetFlags(t, raw, 2, 2)
	if guestOutputBoundaryFlags(t, raw)&2 == 0 {
		t.Fatal("actual protect-from-close flag not set")
	}
	parentPin, pin, duplicate := f.output.parentPin, f.output.pin, f.output.parentDuplicate
	if err := f.output.closeKnown(); err == nil {
		t.Fatal("actual protected CloseHandle unexpectedly succeeded")
	}
	if !f.output.uncertain || !f.output.poisoned || f.output.closed || f.output.read != raw || f.output.parentPin != parentPin || f.output.pin != pin || f.output.parentDuplicate != duplicate || !bytes.Equal(f.output.immutable, canary) {
		t.Fatal("actual failed close lost retained owner state")
	}
	guestOutputBoundaryAssertHeld(t, f.output, true)
	if guestOutputBoundaryFlags(t, raw)&2 == 0 {
		t.Fatal("live protected flag disappeared")
	}
	for _, h := range []syscall.Handle{raw, pin} {
		info, err := guestRawInfo(h)
		if err != nil || info.identity != f.output.identity {
			t.Fatal("retained actual file pin identity changed", err)
		}
	}
	if _, _, err := f.output.wire(); err == nil {
		t.Fatal("uncertain protected owner produced data")
	}
	// No second closeKnown, clear-protection, cleanup deletion or fake VM seal.
}
