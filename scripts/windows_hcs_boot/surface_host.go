//go:build windows && !fixture && go1.24

package main

import (
	"bytes"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"

	"golang.org/x/sys/windows"
)

type surfaceReceipt struct {
	SourceDirectory   string         `json:"synthetic_source_directory_identity"`
	SourceFile        string         `json:"synthetic_source_file_identity"`
	InputSHA          string         `json:"input_sha256"`
	Reply             *transferReply `json:"guest_observations"`
	QuarantineWritten bool           `json:"synthetic_quarantine_written"`
	QuarantineSHA     string         `json:"synthetic_quarantine_sha256"`
}
type surfaceFixture struct {
	source, quarantine *os.Root
	directory, input   *os.File
	packet             transferInput
	receipt            *surfaceReceipt
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
func newSurfaceFixture(root string) (f *surfaceFixture, err error) {
	f = &surfaceFixture{receipt: &surfaceReceipt{}}
	defer func() {
		if err != nil {
			err = errors.Join(err, f.close())
		}
	}()
	for _, name := range []string{"surface-source", "surface-quarantine"} {
		if err = os.Mkdir(filepath.Join(root, name), 0700); err != nil {
			return
		}
	}
	f.source, err = os.OpenRoot(filepath.Join(root, "surface-source"))
	if err != nil {
		return
	}
	f.quarantine, err = os.OpenRoot(filepath.Join(root, "surface-quarantine"))
	if err != nil {
		return
	}
	f.directory, err = f.source.Open(".")
	if err != nil {
		return
	}
	f.receipt.SourceDirectory, err = fixtureIdentity(f.directory, true)
	if err != nil {
		return
	}
	nonce := make([]byte, 16)
	if _, err = rand.Read(nonce); err != nil {
		return
	}
	f.packet.Nonce = hex.EncodeToString(nonce)
	f.packet.Data = []byte("ctm-synthetic:" + f.packet.Nonce)
	f.packet.InputSHA = fixtureHash(f.packet.Data)
	f.receipt.InputSHA = f.packet.InputSHA
	var w *os.File
	w, err = f.source.OpenFile("input.bin", os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return
	}
	_, err = w.Write(f.packet.Data)
	err = errors.Join(err, w.Sync(), w.Close())
	if err != nil {
		return
	}
	f.input, err = f.source.Open("input.bin")
	if err != nil {
		return
	}
	f.receipt.SourceFile, err = fixtureIdentity(f.input, false)
	return
}
func (f *surfaceFixture) close() error {
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
func (f *surfaceFixture) inputBytes() ([]byte, error) { return json.Marshal(f.packet) }
func (f *surfaceFixture) accept(output string) error {
	f.receipt.Reply = nil
	var reply transferReply
	if e := decodeFixture([]byte(output), 8192, &reply); e != nil {
		return e
	}
	if reply.Marker != "CTM_SURFACE_ENTRY" || reply.Nonce != f.packet.Nonce || reply.InputSHA != f.packet.InputSHA || len(reply.Data) > 1024 ||
		!bytes.Equal(reply.Data, bytes.ToUpper(f.packet.Data)) || fixtureHash(reply.Data) != reply.OutputSHA {
		return errors.New("fixture reply identity/hash mismatch")
	}
	if len(reply.Allocations) != 6 || len(reply.Peers) != 3 {
		return errors.New("incomplete socket inventory")
	}
	for i, o := range reply.Allocations {
		if o.Name != socketInventory[i].name || o.CloseError != "" || (o.Created && !o.Closed) {
			return errors.New("allocation identity/close mismatch")
		}
	}
	for i, o := range reply.Peers {
		if o.Name != []string{"tcp4", "tcp6", "unix"}[i] || o.CloseError != "" || (o.Created && !o.Closed) {
			return errors.New("peer identity/close mismatch")
		}
	}
	f.receipt.Reply = &reply
	return nil
}
func (f *surfaceFixture) finishQuarantine(r report) (err error) {
	if !complete(r) || f.receipt.Reply == nil {
		return errors.New("fixture quarantine requires completed owned UVM")
	}
	d, e := fixtureIdentity(f.directory, true)
	if e != nil || d != f.receipt.SourceDirectory {
		return errors.New("synthetic source directory changed")
	}
	id, e := fixtureIdentity(f.input, false)
	if e != nil || id != f.receipt.SourceFile {
		return errors.New("held synthetic source file changed")
	}
	current, e := f.source.Open("input.bin")
	if e != nil {
		return e
	}
	defer func() { err = errors.Join(err, current.Close()) }()
	id, e = fixtureIdentity(current, false)
	if e != nil || id != f.receipt.SourceFile {
		return errors.New("synthetic input name retargeted")
	}
	b, e := io.ReadAll(io.LimitReader(current, 1025))
	if e != nil || len(b) > 1024 || fixtureHash(b) != f.packet.InputSHA {
		return errors.New("synthetic source contents changed")
	}
	w, e := f.quarantine.OpenFile("returned.bin", os.O_RDWR|os.O_CREATE|os.O_EXCL, 0600)
	if e != nil {
		return e
	}
	n, e := w.Write(f.receipt.Reply.Data)
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
	if n != len(f.receipt.Reply.Data) || !bytes.Equal(actual, f.receipt.Reply.Data) {
		return io.ErrShortWrite
	}
	f.receipt.QuarantineWritten = true
	f.receipt.QuarantineSHA = fixtureHash(actual)
	return nil
}
