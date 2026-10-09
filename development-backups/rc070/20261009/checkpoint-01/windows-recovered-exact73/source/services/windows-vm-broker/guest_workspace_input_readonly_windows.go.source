//go:build windows

package main

import (
	"errors"
	"runtime"
	"syscall"
	"unicode/utf16"
	"unsafe"
)

// Freeze the actual input for ordinary runtime readers. An independent readonly
// noDELETE pin survives checked writer close, before strict shareREAD reopening.
// These handles are fields of the already registered guest input owner.
func (f *guestOwnedFile) freezeForWorkload() error {
	if f == nil || f.workloadReadOnly || f.workloadPin != 0 || f.cursor != f.manifest.total {
		return errors.New("guest input workload freeze unavailable")
	}
	if _, e := f.observeInput(f.immutable); e != nil {
		return e
	}
	if e := f.openWorkloadRead(&f.workloadPin, 3); e != nil {
		return e
	}
	if f.cancellation.Err() != nil {
		f.poisoned = true
		return errors.New("guest input writer close cancelled")
	}
	if e := syscall.CloseHandle(f.handle); e != nil {
		f.uncertain, f.poisoned = true, true
		return errors.New("guest input writer close uncertain")
	}
	f.handle = 0
	if e := f.openWorkloadRead(&f.handle, 1); e != nil {
		return e
	}
	if pos, e := syscall.Seek(f.handle, int64(f.cursor), 0); e != nil || uint64(pos) != f.cursor {
		f.poisoned = true
		return errors.New("guest input readonly cursor rejected")
	}
	if _, e := f.observeInput(f.immutable); e != nil {
		return e
	}
	f.workloadReadOnly = true
	return nil
}

func (f *guestOwnedFile) openWorkloadRead(dst *syscall.Handle, share uint32) error {
	if f == nil || f.poisoned || f.uncertain || f.closed || f.cancellation == nil || f.cancellation.Err() != nil ||
		*dst != 0 || f.parentHandle == 0 || !guestLeaf(f.leaf) || (share != 1 && share != 3) {
		return errors.New("guest input readonly open rejected")
	}
	parent, e := guestRawInfo(f.parentHandle)
	if e != nil || !parent.directory || parent.identity != f.parentID {
		f.poisoned = true
		return errors.New("guest input readonly parent conflict")
	}
	wide := append(utf16.Encode([]rune(f.leaf)), 0)
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
	type status struct{ code, information uintptr }
	name := text{uint16((len(wide) - 1) * 2), uint16(len(wide) * 2), &wide[0]}
	a := attrs{root: f.parentHandle, name: &name, attributes: 0x1040}
	a.length = uint32(unsafe.Sizeof(a))
	var result status
	r, _, _ := guestNtCreate.Call(uintptr(unsafe.Pointer(dst)), 0x00100081,
		uintptr(unsafe.Pointer(&a)), uintptr(unsafe.Pointer(&result)), 0, 0x80,
		uintptr(share), 1, 0x00200060, 0, 0)
	runtime.KeepAlive(wide)
	if int32(r) < 0 || int32(result.code) < 0 || result.information != 1 || *dst == 0 || *dst == syscall.InvalidHandle {
		f.poisoned = true
		if *dst != 0 && *dst != syscall.InvalidHandle {
			f.uncertain = true
		} else {
			*dst = 0
		}
		return errors.New("guest input readonly native result rejected")
	}
	info, e := guestRawInfo(*dst)
	if e != nil || info.directory || info.links != 1 || info.identity != f.identity || info.size != f.manifest.total || f.cancellation.Err() != nil {
		f.poisoned = true
		return errors.New("guest input readonly identity or size conflict")
	}
	return nil
}
