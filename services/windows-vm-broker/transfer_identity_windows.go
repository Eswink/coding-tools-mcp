//go:build windows

package main

import (
    "errors"
    "os"
    "runtime"
    "syscall"
)

// Borrow the caller's actual retained handle. No pathname reopen or authority.
// Existing exact-source guestRawInfo observes the full FileId128/volume/attributes.
func observeTransferFile(file *os.File) (guestFileInfo, error) {
    if file == nil { return guestFileInfo{}, errors.New("retained transfer file missing") }
    defer runtime.KeepAlive(file)
    info, err := guestRawInfo(syscall.Handle(file.Fd()))
    if err != nil || info.directory || info.links != 1 || info.size > workspaceMaximum {
        return guestFileInfo{}, errors.New("retained transfer file rejected")
    }
    return info, nil
}
