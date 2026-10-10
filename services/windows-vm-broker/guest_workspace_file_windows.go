//go:build windows

package main

// Guest-realm data evidence only. No native host permission or VM exit issuer.
import (
	"context"
	"errors"
	"os"
	"runtime"
	"strings"
	"sync"
	"syscall"
	"unicode/utf16"
	"unsafe"
)

type guestFileIdentity struct {
	volume uint64
	id     [16]byte
}
type guestFileInfo struct {
	identity  guestFileIdentity
	size      uint64
	links     uint32
	directory bool
}

var guestFileInfoEx = syscall.NewLazyDLL("kernel32.dll").NewProc("GetFileInformationByHandleEx")
var guestNtCreate = syscall.NewLazyDLL("ntdll.dll").NewProc("NtCreateFile")
var guestHeld = struct {
	sync.Mutex
	entries map[*guestOwnedFile]bool
}{entries: make(map[*guestOwnedFile]bool)}

type guestOwnedFile struct {
	parentHandle                                     syscall.Handle
	workloadPin                                      syscall.Handle
	leaf                                             string
	workloadReadOnly                                 bool
	parentID                                         guestFileIdentity
	manifest                                         workspaceStreamManifest
	cancellation                                     context.Context
	handle                                           syscall.Handle
	identity                                         guestFileIdentity
	cursor                                           uint64
	immutable                                        []byte
	poisoned, uncertain, closed, createMayHaveEffect bool
}

func guestRawInfo(handle syscall.Handle) (guestFileInfo, error) {
	var basic syscall.ByHandleFileInformation
	if handle == 0 || handle == syscall.InvalidHandle || syscall.GetFileInformationByHandle(handle, &basic) != nil || basic.FileAttributes&syscall.FILE_ATTRIBUTE_REPARSE_POINT != 0 {
		return guestFileInfo{}, errors.New("guest handle attributes rejected")
	}
	var id struct {
		volume uint64
		fileID [16]byte
	}
	ok, _, _ := guestFileInfoEx.Call(uintptr(handle), 18, uintptr(unsafe.Pointer(&id)), unsafe.Sizeof(id))
	if ok == 0 || id.volume == 0 || id.fileID == ([16]byte{}) {
		return guestFileInfo{}, errors.New("guest FileId128 unavailable")
	}
	return guestFileInfo{identity: guestFileIdentity{id.volume, id.fileID}, size: uint64(basic.FileSizeHigh)<<32 | uint64(basic.FileSizeLow), links: basic.NumberOfLinks, directory: basic.FileAttributes&syscall.FILE_ATTRIBUTE_DIRECTORY != 0}, nil
}
func guestParentIdentity(parent *os.File) (guestFileIdentity, error) {
	if parent == nil {
		return guestFileIdentity{}, errors.New("guest retained parent missing")
	}
	defer runtime.KeepAlive(parent)
	info, e := guestRawInfo(syscall.Handle(parent.Fd()))
	if e != nil || !info.directory {
		return guestFileIdentity{}, errors.New("guest parent is not ordinary directory")
	}
	return info.identity, nil
}
func guestLeaf(name string) bool {
	if len(name) == 0 || len(name) > 120 || name[0] == '.' || name[len(name)-1] == '.' {
		return false
	}
	for _, b := range []byte(name) {
		if !(b >= 'a' && b <= 'z' || b >= 'A' && b <= 'Z' || b >= '0' && b <= '9' || b == '.' || b == '_' || b == '-') {
			return false
		}
	}
	base := strings.ToUpper(strings.Split(name, ".")[0])
	switch base {
	case "CON", "PRN", "AUX", "NUL", "CLOCK$", "CONIN$", "CONOUT$":
		return false
	}
	for _, prefix := range []string{"COM", "LPT"} {
		if len(base) == 4 && strings.HasPrefix(base, prefix) && base[3] >= '1' && base[3] <= '9' {
			return false
		}
	}
	return true
}

// Own an independent, noninherited duplicate of the actual parent object.
// This native data primitive still cannot prove a host workspace grant.
func createGuestWorkspaceFile(ctx context.Context, parent *os.File, parentID guestFileIdentity, name string, m workspaceStreamManifest) (*guestOwnedFile, error) {
	f := &guestOwnedFile{parentID: parentID, manifest: m, cancellation: ctx, leaf: name}
	if ctx == nil || ctx.Err() != nil || !m.valid() || m.direction != 1 || !guestLeaf(name) || parentID.volume == 0 || parentID.id == ([16]byte{}) {
		return f, errors.New("guest file manifest rejected")
	}
	actual, e := guestParentIdentity(parent)
	if e != nil || actual != parentID {
		return f, errors.New("guest parent identity conflict")
	}
	guestHeld.Lock()
	if len(guestHeld.entries) >= 256 {
		guestHeld.Unlock()
		return f, errors.New("guest ownership census full")
	}
	guestHeld.entries[f] = true
	guestHeld.Unlock()
	process, e := syscall.GetCurrentProcess()
	if e != nil {
		_ = f.closeKnown()
		return f, errors.New("guest duplicate process unavailable")
	}
	e = syscall.DuplicateHandle(process, syscall.Handle(parent.Fd()), process, &f.parentHandle, 0, false, 2)
	runtime.KeepAlive(parent)
	if e != nil || f.parentHandle == 0 || f.parentHandle == syscall.InvalidHandle {
		if f.parentHandle != 0 && f.parentHandle != syscall.InvalidHandle {
			f.uncertain = true
		} else {
			f.parentHandle = 0
			_ = f.closeKnown()
		}
		return f, errors.New("guest parent duplication rejected")
	}
	duplicated, e := guestRawInfo(f.parentHandle)
	if e != nil || !duplicated.directory || duplicated.identity != parentID {
		f.poisoned = true
		return f, errors.New("guest duplicate parent identity conflict")
	}
	// Keep a strong owner before physical creation. Native raw child handles have
	// no os.File finalizer; only a confirmed CloseHandle releases this registry.
	var nameUTF16 = append(utf16.Encode([]rune(name)), 0)
	type unicodeString struct {
		length, maximum uint16
		buffer          *uint16
	}
	type objectAttributes struct {
		length            uint32
		root              syscall.Handle
		name              *unicodeString
		attributes        uint32
		security, quality uintptr
	}
	type ioStatus struct{ status, information uintptr }
	text := unicodeString{uint16((len(nameUTF16) - 1) * 2), uint16(len(nameUTF16) * 2), &nameUTF16[0]}
	attrs := objectAttributes{root: f.parentHandle, name: &text, attributes: 0x1040}
	attrs.length = uint32(unsafe.Sizeof(attrs))
	var status ioStatus
	var raw syscall.Handle
	if ctx.Err() != nil {
		f.poisoned = true
		_ = f.closeKnown()
		return f, errors.New("guest cancelled before create")
	}
	f.createMayHaveEffect = true
	r, _, _ := guestNtCreate.Call(uintptr(unsafe.Pointer(&raw)), 0x00100083, uintptr(unsafe.Pointer(&attrs)), uintptr(unsafe.Pointer(&status)), 0, 0x80, 1, 2, 0x00200060, 0, 0)
	runtime.KeepAlive(parent)
	runtime.KeepAlive(nameUTF16)
	f.handle = raw
	if int32(r) < 0 || int32(status.status) < 0 || status.information != 2 || raw == 0 || raw == syscall.InvalidHandle {
		f.poisoned = true
		if raw != 0 && raw != syscall.InvalidHandle {
			f.uncertain = true
		} else {
			f.handle = 0
			_ = f.closeKnown()
		}
		return f, errors.New("guest relative FILE_CREATE result rejected")
	}
	info, e := guestRawInfo(raw)
	if e != nil || info.directory || info.links != 1 || info.size != 0 || info.identity.volume != parentID.volume {
		f.poisoned = true
		return f, errors.New("guest created file identity rejected")
	}
	f.identity = info.identity
	if ctx.Err() != nil {
		f.poisoned = true
		return f, errors.New("guest creation cancelled")
	}
	return f, nil
}
func (f *guestOwnedFile) check() error {
	if f == nil || f.closed || f.poisoned || f.uncertain || f.cancellation == nil || f.cancellation.Err() != nil {
		return errors.New("guest file unavailable or cancelled")
	}
	parent, e := guestRawInfo(f.parentHandle)
	if e != nil || !parent.directory || parent.identity != f.parentID {
		f.poisoned = true
		return errors.New("guest parent changed")
	}
	info, e := guestRawInfo(f.handle)
	if e != nil || info.directory || info.links != 1 || info.identity != f.identity || info.size != f.cursor {
		f.poisoned = true
		return errors.New("guest file changed")
	}
	pos, e := syscall.Seek(f.handle, 0, 1)
	if e != nil || pos < 0 || uint64(pos) != f.cursor {
		f.poisoned = true
		return errors.New("guest file cursor changed")
	}
	return nil
}
func (f *guestOwnedFile) writeChunk(data []byte) error {
	if f.workloadReadOnly || len(data) == 0 || len(data) > workspaceChunk || f.cursor+uint64(len(data)) > f.manifest.total {
		f.poisoned = true
		return errors.New("guest write bound")
	}
	if e := f.check(); e != nil {
		return e
	}
	var n uint32
	e := syscall.WriteFile(f.handle, data, &n, nil)
	if e != nil || int(n) != len(data) {
		f.poisoned = true
		return errors.New("guest write failed")
	}
	f.cursor += uint64(n)
	if e = f.check(); e != nil {
		return e
	}
	return nil
}
func (f *guestOwnedFile) closeKnown() error {
	if f == nil || f.closed {
		return nil
	}
	if f.uncertain {
		return errors.New("guest close already uncertain")
	}
	if f.handle != 0 {
		if e := syscall.CloseHandle(f.handle); e != nil {
			f.uncertain = true
			f.poisoned = true
			return errors.New("guest CloseHandle uncertain")
		}
		f.handle = 0
	}
	if f.workloadPin != 0 {
		if e := syscall.CloseHandle(f.workloadPin); e != nil {
			f.uncertain, f.poisoned = true, true
			return errors.New("guest workload pin CloseHandle uncertain")
		}
		f.workloadPin = 0
	}
	if f.parentHandle != 0 {
		if e := syscall.CloseHandle(f.parentHandle); e != nil {
			f.uncertain = true
			f.poisoned = true
			return errors.New("guest parent CloseHandle uncertain")
		}
		f.parentHandle = 0
	}
	f.closed = true
	f.immutable = nil
	guestHeld.Lock()
	delete(guestHeld.entries, f)
	guestHeld.Unlock()
	return nil
}
