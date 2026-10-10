//go:build windows

package main

// Unregistered guest data mechanism. This owner is not a host grant or VM seal.
import (
	"context"
	"errors"
	"os"
	"runtime"
	"sync"
	"syscall"
	"unicode/utf16"
	"unsafe"
)

var guestOutputHeld = struct {
	sync.Mutex
	entries map[*guestOwnedOutput]bool
}{entries: make(map[*guestOwnedOutput]bool)}

type guestOwnedOutput struct {
	ctx                                           context.Context
	input                                         *guestOwnedFile
	parentID, identity                            guestFileIdentity
	leaf                                          string
	parentDuplicate, parentPin, writer, pin, read syscall.Handle
	immutable                                     []byte
	evidence                                      guestOutputEvidence
	poisoned, uncertain, closed, frozen, consumed bool
	createMayHaveEffect                           bool
}

// Native output handles intentionally have no os.File finalizers. The strong
// registry owner exists before duplication/open/create; an unwind retains it.
func createGuestWorkspaceOutput(ctx context.Context, parent *os.File, parentID guestFileIdentity, leaf string, input *guestOwnedFile) (f *guestOwnedOutput, err error) {
	f = &guestOwnedOutput{ctx: ctx, parentID: parentID, leaf: leaf, input: input}
	defer f.markPanic()
	if ctx == nil || ctx.Err() != nil || input == nil || !guestLeaf(leaf) || parentID.volume == 0 || parentID.id == ([16]byte{}) {
		return f, errors.New("guest output arguments rejected")
	}
	actual, e := guestParentIdentity(parent)
	if e != nil || actual != parentID || input.parentID != parentID || input.manifest.direction != 1 || input.identity.id == ([16]byte{}) {
		return f, errors.New("guest output input/parent binding rejected")
	}
	if _, e = input.observeInput(input.immutable); e != nil {
		return f, errors.New("guest output actual input not observed")
	}
	guestOutputHeld.Lock()
	if len(guestOutputHeld.entries) >= 256 {
		guestOutputHeld.Unlock()
		return f, errors.New("guest output owner census full")
	}
	guestOutputHeld.entries[f] = true
	guestOutputHeld.Unlock()
	process, e := syscall.GetCurrentProcess()
	if e != nil {
		return f, errors.New("guest output duplicate process unavailable")
	}
	e = syscall.DuplicateHandle(process, syscall.Handle(parent.Fd()), process, &f.parentDuplicate, 0, false, 2)
	runtime.KeepAlive(parent)
	if e != nil || f.parentDuplicate == 0 || f.parentDuplicate == syscall.InvalidHandle {
		f.poisoned = true
		if f.parentDuplicate != 0 && f.parentDuplicate != syscall.InvalidHandle {
			f.uncertain = true
		} else {
			f.parentDuplicate = 0
		}
		return f, errors.New("guest output parent duplication rejected")
	}
	dup, e := guestRawInfo(f.parentDuplicate)
	if e != nil || !dup.directory || dup.identity != parentID {
		f.poisoned = true
		return f, errors.New("guest output parent duplicate changed")
	}
	// Duplicate alone cannot prove its sharing mode. Independently open the actual
	// directory object with no DELETE sharing, then compare its complete identity.
	if e = f.openInto(&f.parentPin, f.parentDuplicate, ".", true, 0x00100081, 3, 1); e != nil {
		return f, e
	}
	if e = f.checkParent(); e != nil {
		return f, e
	}
	if e = f.openInto(&f.writer, f.parentPin, leaf, false, 0x00100082, 3, 2); e != nil {
		return f, e
	}
	created, e := guestRawInfo(f.writer)
	if e != nil || created.directory || created.links != 1 || created.size != 0 || created.identity.volume != parentID.volume {
		f.poisoned = true
		return f, errors.New("guest output created file rejected")
	}
	f.identity = created.identity
	if e = f.openInto(&f.pin, f.parentPin, leaf, false, 0x00100081, 3, 1); e != nil {
		return f, e
	}
	if _, e = f.checkPin(); e != nil {
		return f, e
	}
	if ctx.Err() != nil {
		f.poisoned = true
		return f, errors.New("guest output create cancelled")
	}
	return f, nil
}

func (f *guestOwnedOutput) markPanic() {
	if r := recover(); r != nil {
		f.poisoned = true
		panic(r)
	}
}

// dst is a field of this already registered owner, so the actual returned raw
// value is retained even if control unwinds before validation. No absolute path.
func (f *guestOwnedOutput) openInto(dst *syscall.Handle, parent syscall.Handle, name string, directory bool, access, share, disposition uint32) error {
	if f.ctx.Err() != nil || *dst != 0 || parent == 0 || (directory && name != ".") || (!directory && !guestLeaf(name)) || (share != 1 && share != 3) || (disposition != 1 && disposition != 2) {
		f.poisoned = true
		return errors.New("guest output relative open rejected")
	}
	wide := append(utf16.Encode([]rune(name)), 0)
	type text struct {
		length, maximum uint16
		buffer          *uint16
	}
	type attrs struct {
		length            uint32
		root              syscall.Handle
		name              *text
		attributes        uint32
		security, quality uintptr
	}
	type ioStatus struct{ status, information uintptr }
	t := text{uint16((len(wide) - 1) * 2), uint16(len(wide) * 2), &wide[0]}
	a := attrs{root: parent, name: &t, attributes: 0x1040}
	a.length = uint32(unsafe.Sizeof(a))
	var status ioStatus
	options := uint32(0x00200060)
	if directory {
		options = 0x00200021
	}
	if disposition == 2 {
		f.createMayHaveEffect = true
	}
	r, _, _ := guestNtCreate.Call(uintptr(unsafe.Pointer(dst)), uintptr(access), uintptr(unsafe.Pointer(&a)), uintptr(unsafe.Pointer(&status)), 0, 0x80, uintptr(share), uintptr(disposition), uintptr(options), 0, 0)
	runtime.KeepAlive(wide)
	want := uintptr(1)
	if disposition == 2 {
		want = 2
	}
	if int32(r) < 0 || int32(status.status) < 0 || status.information != want || *dst == 0 || *dst == syscall.InvalidHandle {
		f.poisoned = true
		if *dst != 0 && *dst != syscall.InvalidHandle {
			f.uncertain = true
		} else {
			*dst = 0
		}
		return errors.New("guest output NT result rejected")
	}
	if f.ctx.Err() != nil {
		f.poisoned = true
		return errors.New("guest output open cancelled")
	}
	return nil
}

func (f *guestOwnedOutput) checkParent() error {
	if f == nil || f.closed || f.poisoned || f.uncertain || f.ctx == nil || f.ctx.Err() != nil {
		return errors.New("guest output owner unavailable")
	}
	for _, h := range []syscall.Handle{f.parentDuplicate, f.parentPin} {
		info, e := guestRawInfo(h)
		if e != nil || !info.directory || info.identity != f.parentID {
			f.poisoned = true
			return errors.New("guest output parent identity changed")
		}
	}
	return nil
}

func (f *guestOwnedOutput) checkPin() (guestFileInfo, error) {
	if e := f.checkParent(); e != nil {
		return guestFileInfo{}, e
	}
	info, e := guestRawInfo(f.pin)
	if e != nil || info.directory || info.links != 1 || info.identity != f.identity || info.identity.volume != f.parentID.volume || info.size > workspaceMaximum {
		f.poisoned = true
		return guestFileInfo{}, errors.New("guest output pin changed or out of bounds")
	}
	return info, nil
}

func (f *guestOwnedOutput) closeKnown() error {
	if f == nil || f.closed {
		return nil
	}
	defer f.markPanic()
	if f.uncertain {
		return errors.New("guest output close already uncertain")
	}
	// The noDELETE parent and original pin live until all file handles close.
	for _, h := range []*syscall.Handle{&f.writer, &f.read, &f.pin, &f.parentPin, &f.parentDuplicate} {
		if *h != 0 {
			if e := syscall.CloseHandle(*h); e != nil {
				f.uncertain, f.poisoned = true, true
				return errors.New("guest output CloseHandle uncertain")
			}
			*h = 0
		}
	}
	f.closed = true
	f.immutable = nil
	guestOutputHeld.Lock()
	delete(guestOutputHeld.entries, f)
	guestOutputHeld.Unlock()
	return nil
}
