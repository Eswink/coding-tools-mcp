//go:build windows

package main

import (
	"crypto/sha256"
	"errors"
	"syscall"
)

// Data only: both IDs come from actual held guest files. It is serializable
// neither as a native root grant nor as a wholeVM retirement capability.
type guestOutputEvidence struct {
	input  guestInputEvidence
	output guestInputEvidence
}

// The future actual guest runtime must stop its command before calling freeze.
// This unregistered method does not prove process exit, memory-map quiescence,
// native IO retirement, VM exit, or permission. Never mint a seal from it.
func (f *guestOwnedOutput) freeze() (guestOutputEvidence, error) {
	if f == nil || f.frozen || f.consumed || f.writer == 0 {
		return guestOutputEvidence{}, errors.New("guest output freeze unavailable")
	}
	defer f.markPanic()
	if _, e := f.checkPin(); e != nil {
		return guestOutputEvidence{}, e
	}
	input, e := f.input.observeInput(f.input.immutable)
	if e != nil || input.binding != f.input.manifest.binding || input.parent != f.parentID {
		f.poisoned = true
		return guestOutputEvidence{}, errors.New("guest input changed before output freeze")
	}
	if f.ctx.Err() != nil {
		f.poisoned = true
		return guestOutputEvidence{}, errors.New("guest output flush cancelled")
	}
	if e = syscall.FlushFileBuffers(f.writer); e != nil || f.ctx.Err() != nil {
		f.poisoned = true
		return guestOutputEvidence{}, errors.New("guest output flush failed or cancelled")
	}
	if e = syscall.CloseHandle(f.writer); e != nil {
		f.poisoned, f.uncertain = true, true
		return guestOutputEvidence{}, errors.New("guest output writer close uncertain")
	}
	f.writer = 0
	// Surviving WRITE_DATA/APPEND_DATA handles conflict with this sharing mode.
	// Original readonly pin denies DELETE throughout; failure is never downgraded.
	if e = f.openInto(&f.read, f.parentPin, f.leaf, false, 0x00100081, 1, 1); e != nil {
		return guestOutputEvidence{}, e
	}
	info, e := f.checkPin()
	if e != nil {
		return guestOutputEvidence{}, e
	}
	if e = f.checkFrozenRead(info.size, 0); e != nil {
		return guestOutputEvidence{}, e
	}
	// Store the allocation in the strong owner before native reads. A partial
	// read, panic, cancellation or later unknown close cannot discard its bytes.
	f.immutable = make([]byte, int(info.size))
	for offset := uint64(0); offset < info.size; {
		size := uint64(workspaceChunk)
		if info.size-offset < size {
			size = info.size - offset
		}
		if e = f.checkFrozenRead(info.size, offset); e != nil {
			return guestOutputEvidence{}, e
		}
		var n uint32
		e = syscall.ReadFile(f.read, f.immutable[int(offset):int(offset+size)], &n, nil)
		if e != nil || uint64(n) != size {
			f.poisoned = true
			return guestOutputEvidence{}, errors.New("guest output bounded read failed")
		}
		offset += uint64(n)
		if e = f.checkFrozenRead(info.size, offset); e != nil {
			return guestOutputEvidence{}, e
		}
	}
	if e = f.checkFrozenRead(info.size, info.size); e != nil {
		return guestOutputEvidence{}, e
	}
	var extra [1]byte
	var n uint32
	e = syscall.ReadFile(f.read, extra[:], &n, nil)
	if n != 0 || (e != nil && e != syscall.ERROR_HANDLE_EOF) {
		f.poisoned = true
		return guestOutputEvidence{}, errors.New("guest output exact EOF rejected")
	}
	if e = f.checkFrozenRead(info.size, info.size); e != nil {
		return guestOutputEvidence{}, e
	}
	digest := sha256.Sum256(f.immutable)
	inputAfter, e := f.input.observeInput(f.input.immutable)
	if e != nil || inputAfter != input || f.ctx.Err() != nil {
		f.poisoned = true
		return guestOutputEvidence{}, errors.New("guest input changed or cancelled after output read")
	}
	f.evidence = guestOutputEvidence{input: input, output: guestInputEvidence{binding: input.binding, identity: f.identity, parent: f.parentID, size: info.size, digest: digest}}
	f.frozen = true
	return f.evidence, nil
}

func (f *guestOwnedOutput) checkFrozenRead(size, cursor uint64) error {
	info, e := f.checkPin()
	if e != nil {
		return e
	}
	read, e := guestRawInfo(f.read)
	if e != nil || read.directory || read.links != 1 || read.identity != f.identity || read.size != size || info.size != size {
		f.poisoned = true
		return errors.New("guest output readonly identity/size conflict")
	}
	pos, e := syscall.Seek(f.read, 0, 1)
	if e != nil || pos < 0 || uint64(pos) != cursor {
		f.poisoned = true
		return errors.New("guest output readonly cursor conflict")
	}
	if f.ctx.Err() != nil {
		f.poisoned = true
		return errors.New("guest output native observation cancelled")
	}
	return nil
}

func (f *guestOwnedOutput) wire() (guestOutputEvidence, []byte, error) {
	if f == nil || !f.frozen || f.consumed {
		return guestOutputEvidence{}, nil, errors.New("guest output wire unavailable or already consumed")
	}
	defer f.markPanic()
	if e := f.checkFrozenRead(f.evidence.output.size, f.evidence.output.size); e != nil {
		return guestOutputEvidence{}, nil, e
	}
	input, e := f.input.observeInput(f.input.immutable)
	if e != nil || input != f.evidence.input || uint64(len(f.immutable)) != f.evidence.output.size || sha256.Sum256(f.immutable) != f.evidence.output.digest {
		f.poisoned = true
		return guestOutputEvidence{}, nil, errors.New("guest output final data binding conflict")
	}
	m := workspaceStreamManifest{binding: f.evidence.output.binding, direction: 2, total: f.evidence.output.size, digest: f.evidence.output.digest}
	if f.ctx.Err() != nil {
		f.poisoned = true
		return guestOutputEvidence{}, nil, errors.New("guest output encode cancelled")
	}
	wire, e := workspaceEncode(m, f.immutable)
	if e != nil || f.ctx.Err() != nil {
		f.poisoned = true
		return guestOutputEvidence{}, nil, errors.New("guest output encode failed or cancelled")
	}
	f.consumed = true
	return f.evidence, wire, nil
}
