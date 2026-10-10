//go:build windows

package main

// Scratch-only diagnostic for run 38032877845: reports raw NTSTATUS/Information for the
// relative opens used by createGuestWorkspaceOutput. Never copied into the SUT or bundle.
import (
	"os"
	"syscall"
	"testing"
	"unicode/utf16"
	"unsafe"
)

func TestDiagRelativeOpens(t *testing.T) {
	dir, _ := os.MkdirTemp(os.Getenv("RUNNER_TEMP"), "ctm-ntdiag-")
	p, _ := syscall.UTF16PtrFromString(dir)
	parent, e := syscall.CreateFile(p, 0x00100081, 7, nil, 3, 0x02000000, 0)
	if e != nil {
		t.Fatal(e)
	}
	open := func(label string, root syscall.Handle, name string, access, share, disp, opts uint32) syscall.Handle {
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
		var st struct{ status, information uintptr }
		tx := text{uint16((len(wide) - 1) * 2), uint16(len(wide) * 2), &wide[0]}
		a := attrs{root: root, name: &tx, attributes: 0x1040}
		a.length = uint32(unsafe.Sizeof(a))
		var h syscall.Handle
		r, _, _ := guestNtCreate.Call(uintptr(unsafe.Pointer(&h)), uintptr(access), uintptr(unsafe.Pointer(&a)), uintptr(unsafe.Pointer(&st)), 0, 0x80, uintptr(share), uintptr(disp), uintptr(opts), 0, 0)
		t.Logf("DIAG %s: r=0x%08x iosb.status=0x%08x info=%d handle=%v", label, uint32(r), uint32(st.status), st.information, h != 0)
		return h
	}
	pinDot := open("parentPin name='.' share=3", parent, ".", 0x00100081, 3, 1, 0x00200021)
	pinEmpty := open("parentPin name='' share=3", parent, "", 0x00100081, 3, 1, 0x00200021)
	root := pinDot
	if root == 0 {
		root = pinEmpty
	}
	if root == 0 {
		root = parent
	}
	open("writer create output.bin share=3", root, "output.bin", 0x00100082, 3, 2, 0x00200060)
}
