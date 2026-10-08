//go:build windows && !guest && go1.24

package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"

	"golang.org/x/sys/windows"
)

type syntheticRoot struct {
	source, quarantine             *os.Root
	directory, input               *os.File
	directoryID, inputID, inputSHA string
	data, returned                 []byte
}

func fixtureIdentity(f *os.File, dir bool) (string, error) {
	var info windows.ByHandleFileInformation
	if e := windows.GetFileInformationByHandle(windows.Handle(f.Fd()), &info); e != nil {
		return "", e
	}
	if info.FileAttributes&windows.FILE_ATTRIBUTE_REPARSE_POINT != 0 || (info.FileAttributes&windows.FILE_ATTRIBUTE_DIRECTORY != 0) != dir {
		return "", errors.New("unexpected fixture file type")
	}
	if info.FileIndexHigh == 0 && info.FileIndexLow == 0 {
		return "", errors.New("fixture identity unavailable")
	}
	return fmt.Sprintf("%08x:%08x%08x", info.VolumeSerialNumber, info.FileIndexHigh, info.FileIndexLow), nil
}
func newSyntheticRoot(root, session string) (f *syntheticRoot, err error) {
	f = &syntheticRoot{data: []byte("ctm-synthetic:" + session)}
	f.inputSHA = fixtureHash(f.data)
	defer func() {
		if err != nil {
			err = errors.Join(err, f.close())
		}
	}()
	for _, name := range []string{"synthetic-source", "quarantine"} {
		if err = os.Mkdir(filepath.Join(root, name), 0700); err != nil {
			return
		}
	}
	f.source, err = os.OpenRoot(filepath.Join(root, "synthetic-source"))
	if err != nil {
		return
	}
	f.quarantine, err = os.OpenRoot(filepath.Join(root, "quarantine"))
	if err != nil {
		return
	}
	f.directory, err = f.source.Open(".")
	if err != nil {
		return
	}
	f.directoryID, err = fixtureIdentity(f.directory, true)
	if err != nil {
		return
	}
	w, e := f.source.OpenFile("input.bin", os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if e != nil {
		err = e
		return
	}
	n, e := w.Write(f.data)
	err = errors.Join(e, w.Sync(), w.Close())
	if n != len(f.data) {
		err = errors.Join(err, io.ErrShortWrite)
	}
	if err != nil {
		return
	}
	f.input, err = f.source.Open("input.bin")
	if err != nil {
		return
	}
	f.inputID, err = fixtureIdentity(f.input, false)
	return
}
func fixtureHash(data []byte) string { sum := sha256.Sum256(data); return hex.EncodeToString(sum[:]) }
func (f *syntheticRoot) close() error {
	var err error
	for _, c := range []io.Closer{f.input, f.directory, f.source, f.quarantine} {
		switch v := c.(type) {
		case *os.File:
			if v == nil {
				continue
			}
		case *os.Root:
			if v == nil {
				continue
			}
		}
		err = errors.Join(err, c.Close())
	}
	return err
}
func (f *syntheticRoot) acceptGuest(g GuestResult) error {
	data, e := base64.StdEncoding.Strict().DecodeString(g.DataBase64)
	if e != nil || len(data) > 1024 || g.InputSHA256 != f.inputSHA || g.OutputSHA256 != fixtureHash(data) || !bytes.Equal(data, bytes.ToUpper(f.data)) {
		return errors.New("synthetic guest data/hash mismatch")
	}
	f.returned = append([]byte(nil), data...)
	return nil
}
func (f *syntheticRoot) finish(c *Cleanup, cancelled bool) (err error) {
	if !lifecycleComplete(*c) {
		return errors.New("quarantine requires whole VM and IO completion")
	}
	d, e := fixtureIdentity(f.directory, true)
	if e != nil || d != f.directoryID {
		return errors.New("held directory identity changed")
	}
	id, e := fixtureIdentity(f.input, false)
	if e != nil || id != f.inputID {
		return errors.New("held input identity changed")
	}
	current, e := f.source.Open("input.bin")
	if e != nil {
		return e
	}
	defer func() { err = errors.Join(err, current.Close()) }()
	id, e = fixtureIdentity(current, false)
	if e != nil || id != f.inputID {
		return errors.New("synthetic input name changed")
	}
	b, e := io.ReadAll(io.LimitReader(current, 1025))
	if e != nil || len(b) > 1024 || fixtureHash(b) != f.inputSHA {
		return errors.New("synthetic input contents changed")
	}
	c.InputSHA256 = f.inputSHA
	if cancelled {
		c.Quarantine = "withheld"
		c.OutputSHA256 = ""
		return nil
	}
	if f.returned == nil {
		return errors.New("guest result not accepted")
	}
	w, e := f.quarantine.OpenFile("returned.bin", os.O_RDWR|os.O_CREATE|os.O_EXCL, 0600)
	if e != nil {
		return e
	}
	n, e := w.Write(f.returned)
	e = errors.Join(e, w.Sync())
	var actual []byte
	if e == nil {
		_, e = w.Seek(0, io.SeekStart)
	}
	if e == nil {
		actual, e = io.ReadAll(io.LimitReader(w, 1025))
	}
	e = errors.Join(e, w.Close())
	if e != nil {
		return e
	}
	if n != len(f.returned) || !bytes.Equal(actual, f.returned) {
		return io.ErrShortWrite
	}
	c.Quarantine = "written"
	c.OutputSHA256 = fixtureHash(actual)
	return nil
}
func lifecycleComplete(c Cleanup) bool {
	return c.TerminateOK && c.WholeVMExited && c.ExitOK && c.CloseOK && c.GuestIOJoined && c.OwnedDataRetained && !c.NetworkDenialProven && !c.WorkspaceIntegration && !c.ProductionAdmission && len(c.Errors) == 0
}
func completeCleanup(c Cleanup, cancelled bool) bool {
	if !lifecycleComplete(c) || len(c.InputSHA256) != 64 {
		return false
	}
	if cancelled {
		return c.Quarantine == "withheld" && c.OutputSHA256 == ""
	}
	return c.Quarantine == "written" && len(c.OutputSHA256) == 64
}
