//go:build windows

package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"errors"
	"io"
	"os"
	"syscall"
)

// Serializable *data evidence* could be added to a future guest result. These
// values are not native root authorization or an independent wholeVM witness.
type guestInputEvidence struct {
	binding  [32]byte
	identity guestFileIdentity
	parent   guestFileIdentity
	size     uint64
	digest   [32]byte
}

func receiveGuestWorkspaceInput(ctx context.Context, parent *os.File, parentID guestFileIdentity, name string, m workspaceStreamManifest, reader io.Reader) (*guestOwnedFile, guestInputEvidence, error) {
	if reader == nil {
		return nil, guestInputEvidence{}, errors.New("guest input reader missing")
	}
	file, e := createGuestWorkspaceFile(ctx, parent, parentID, name, m)
	if e != nil {
		return file, guestInputEvidence{}, e
	}
	stream, e := newWorkspaceStream(ctx, m)
	if e != nil {
		return file, guestInputEvidence{}, e
	}
	if e = stream.readAll(reader, file.writeChunk); e != nil {
		file.poisoned = true
		return file, guestInputEvidence{}, e
	}
	approved, e := stream.dataCopy()
	if e != nil {
		file.poisoned = true
		return file, guestInputEvidence{}, e
	}
	if e = syscall.FlushFileBuffers(file.handle); e != nil {
		file.poisoned = true
		return file, guestInputEvidence{}, errors.New("guest flush failed")
	}
	evidence, e := file.observeInput(approved)
	return file, evidence, e
}
func (f *guestOwnedFile) observeInput(approved []byte) (guestInputEvidence, error) {
	if e := f.check(); e != nil {
		return guestInputEvidence{}, e
	}
	if f.cursor != f.manifest.total || uint64(len(approved)) != f.manifest.total || sha256.Sum256(approved) != f.manifest.digest {
		f.poisoned = true
		return guestInputEvidence{}, errors.New("guest approved bytes conflict")
	}
	if pos, e := syscall.Seek(f.handle, 0, 0); e != nil || pos != 0 {
		f.poisoned = true
		return guestInputEvidence{}, errors.New("guest read seek failed")
	}
	observed := make([]byte, 0, len(approved))
	remaining := f.manifest.total
	for remaining > 0 {
		if f.cancellation.Err() != nil {
			f.poisoned = true
			return guestInputEvidence{}, errors.New("guest read cancelled")
		}
		size := uint64(workspaceChunk)
		if remaining < size {
			size = remaining
		}
		buffer := make([]byte, int(size))
		var n uint32
		if e := syscall.ReadFile(f.handle, buffer, &n, nil); e != nil || uint64(n) != size {
			f.poisoned = true
			return guestInputEvidence{}, errors.New("guest bounded read failed")
		}
		observed = append(observed, buffer...)
		remaining -= uint64(n)
		if f.cancellation.Err() != nil {
			f.poisoned = true
			return guestInputEvidence{}, errors.New("guest read cancelled")
		}
	}
	if f.cancellation.Err() != nil {
		f.poisoned = true
		return guestInputEvidence{}, errors.New("guest EOF read cancelled")
	}
	var extra [1]byte
	var n uint32
	e := syscall.ReadFile(f.handle, extra[:], &n, nil)
	if n != 0 || (e != nil && e != syscall.ERROR_HANDLE_EOF) {
		f.poisoned = true
		return guestInputEvidence{}, errors.New("guest exact EOF rejected")
	}
	if !bytes.Equal(observed, approved) || sha256.Sum256(observed) != f.manifest.digest {
		f.poisoned = true
		return guestInputEvidence{}, errors.New("guest same-handle hash conflict")
	}
	if e = f.check(); e != nil {
		return guestInputEvidence{}, e
	}
	f.immutable = bytes.Clone(observed)
	if f.cancellation.Err() != nil {
		f.poisoned = true
		return guestInputEvidence{}, errors.New("guest cancelled before evidence")
	}
	return guestInputEvidence{binding: f.manifest.binding, identity: f.identity, parent: f.parentID, size: f.manifest.total, digest: f.manifest.digest}, nil
}
