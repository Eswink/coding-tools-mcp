//go:build windows && guest

package main

import (
	"errors"
	"os"
	"runtime"
	"strings"
	"syscall"
	"unicode/utf16"
	"unsafe"
)

// All raw values belong to the registered whole guest run before native effects.
// These guest-realm paths/IDs are DATA, not an opened host workspace authority.
func (r *guestWorkspaceRun) openRoot() error {
	wide, e := syscall.UTF16PtrFromString(r.realm.path)
	if e != nil {
		return errors.New("guest fixed root rejected")
	}
	r.base, e = syscall.CreateFile(wide, 0x00100087, syscall.FILE_SHARE_READ|syscall.FILE_SHARE_WRITE, nil, syscall.OPEN_EXISTING, syscall.FILE_FLAG_BACKUP_SEMANTICS|syscall.FILE_FLAG_OPEN_REPARSE_POINT, 0)
	if e != nil || r.base == 0 || r.base == syscall.InvalidHandle {
		if r.base != 0 && r.base != syscall.InvalidHandle {
			r.uncertain = true
		} else {
			r.base = 0
		}
		return errors.New("guest fixed root unavailable")
	}
	base, e := guestRawInfo(r.base)
	if e != nil || !base.directory {
		return errors.New("guest fixed root is not ordinary directory")
	}
	if r.ctx.Err() != nil {
		return errors.New("guest root cancelled")
	}
	leaf := "ctm-workspace-" + strings.ReplaceAll(r.control.Operation, "-", "")
	wideName := append(utf16.Encode([]rune(leaf)), 0)
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
	name := text{uint16((len(wideName) - 1) * 2), uint16(len(wideName) * 2), &wideName[0]}
	a := attrs{root: r.base, name: &name, attributes: 0x1040}
	a.length = uint32(unsafe.Sizeof(a))
	var result status
	r.path = r.realm.path + `\` + leaf
	r.createMayHaveEffect = true
	code, _, _ := guestNtCreate.Call(uintptr(unsafe.Pointer(&r.parentRaw)), 0x00100083, uintptr(unsafe.Pointer(&a)), uintptr(unsafe.Pointer(&result)), 0, 0x10, 3, 2, 0x00200021, 0, 0)
	runtime.KeepAlive(wideName)
	if int32(code) < 0 || int32(result.code) < 0 || result.information != 2 || r.parentRaw == 0 || r.parentRaw == syscall.InvalidHandle {
		r.uncertain = true
		if r.parentRaw != 0 && r.parentRaw != syscall.InvalidHandle {
			r.uncertain = true
		} else {
			r.parentRaw = 0
		}
		return errors.New("guest relative operation directory create rejected")
	}
	child, e := guestRawInfo(r.parentRaw)
	if e != nil || !child.directory || child.identity.volume != base.identity.volume || r.ctx.Err() != nil {
		return errors.New("guest operation directory identity rejected")
	}
	r.parentID = child.identity
	r.parent = os.NewFile(uintptr(r.parentRaw), r.path)
	if r.parent == nil {
		return errors.New("guest operation directory provider unavailable")
	}
	return nil
}

func (r *guestWorkspaceRun) closeSources() error {
	if r.uncertain {
		return errors.New("guest run source close already uncertain")
	}
	for _, close := range []func() error{
		func() error {
			if r.output != nil {
				return r.output.closeKnown()
			}
			return nil
		},
		func() error {
			if r.input != nil {
				return r.input.closeKnown()
			}
			return nil
		},
	} {
		if e := close(); e != nil {
			r.uncertain = true
			return errors.New("guest run child close uncertain")
		}
	}
	if r.parent != nil {
		if e := r.parent.Close(); e != nil {
			r.uncertain = true
			return errors.New("guest run parent provider close uncertain")
		}
		r.parent = nil
		r.parentRaw = 0
	} else if r.parentRaw != 0 {
		if e := syscall.CloseHandle(r.parentRaw); e != nil {
			r.uncertain = true
			return errors.New("guest run raw parent close uncertain")
		}
		r.parentRaw = 0
	}
	if r.base != 0 {
		if e := syscall.CloseHandle(r.base); e != nil {
			r.uncertain = true
			return errors.New("guest run base close uncertain")
		}
		r.base = 0
	}
	r.sourcesClosed = true
	return nil
}
