//go:build linux

package main

import (
    "errors"
    "os"
    "testing"
)
func observeTransferFile(file *os.File) error {
    return errors.New("Linux data tests cannot issue Windows native identity")
}
func TestLinuxTransferCannotIssueNativeFileIdentity(t *testing.T) {
    if observeTransferFile(nil) == nil { t.Fatal("Linux cannot produce native FileId128 permission") }
}
