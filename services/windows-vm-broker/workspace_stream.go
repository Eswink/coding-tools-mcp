package main

// V2 data-only protocol. It does not alter the existing synthetic JSON channel,
// issue a native grant or deserialize any retirement/permission capability.
import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/binary"
	"errors"
	"io"
)

const workspaceChunk = 32768
const workspaceHeader = 72
const workspaceMaximum = 1048576
const workspaceFramedMaximum = workspaceMaximum + 33*workspaceHeader

type workspaceStreamManifest struct {
	binding   [32]byte
	direction byte
	total     uint64
	digest    [32]byte
}

func (m workspaceStreamManifest) valid() bool {
	return m.binding != ([32]byte{}) && (m.direction == 1 || m.direction == 2) && m.total <= workspaceMaximum
}

type workspaceStream struct {
	manifest     workspaceStreamManifest
	cancellation context.Context
	sequence     uint32
	offset       uint64
	framed       int
	data         []byte
	state        byte // 1 reading, 2 final-awaiting-EOF, 3 complete, 4 consumed, 0 poisoned.
}

func newWorkspaceStream(ctx context.Context, m workspaceStreamManifest) (*workspaceStream, error) {
	s := &workspaceStream{manifest: m, cancellation: ctx}
	if ctx == nil || !m.valid() || ctx.Err() != nil {
		return s, errors.New("workspace manifest rejected")
	}
	s.state = 1
	return s, nil
}
func (s *workspaceStream) reject(message string) error { s.state = 0; return errors.New(message) }
func (s *workspaceStream) accept(frame []byte) ([]byte, error) {
	if s.state != 1 || s.cancellation.Err() != nil {
		return nil, s.reject("workspace stream terminal or cancelled")
	}
	m := s.manifest
	if len(frame) < workspaceHeader || !bytes.Equal(frame[:8], []byte("CTMWIO02")) || frame[8] != m.direction ||
		frame[9] > 1 || frame[10] != 0 || frame[11] != 0 || !bytes.Equal(frame[36:40], []byte{0, 0, 0, 0}) ||
		!bytes.Equal(frame[40:72], m.binding[:]) {
		return nil, s.reject("workspace header rejected")
	}
	n := binary.LittleEndian.Uint32(frame[32:36])
	if n > workspaceChunk || len(frame) != workspaceHeader+int(n) || s.sequence > 32 ||
		binary.LittleEndian.Uint32(frame[12:16]) != s.sequence || binary.LittleEndian.Uint64(frame[16:24]) != s.offset ||
		binary.LittleEndian.Uint64(frame[24:32]) != m.total || s.framed+len(frame) > workspaceFramedMaximum {
		return nil, s.reject("workspace sequence length or budget rejected")
	}
	final := frame[9] == 1
	if final {
		if n != 0 || s.offset != m.total || sha256.Sum256(s.data) != m.digest {
			return nil, s.reject("workspace final hash or EOF boundary rejected")
		}
		s.state = 2
	} else {
		if n == 0 || s.sequence == 32 || s.offset+uint64(n) > m.total {
			return nil, s.reject("workspace data boundary rejected")
		}
		s.data = append(s.data, frame[workspaceHeader:]...)
		s.offset += uint64(n)
	}
	s.sequence++
	s.framed += len(frame)
	if s.cancellation.Err() != nil {
		return nil, s.reject("workspace stream cancelled")
	}
	return bytes.Clone(frame[workspaceHeader:]), nil
}
func (s *workspaceStream) eof() error {
	if s.state != 2 || s.cancellation.Err() != nil {
		return s.reject("workspace real EOF required")
	}
	s.state = 3
	return nil
}
func (s *workspaceStream) dataCopy() ([]byte, error) {
	if s.state != 3 || s.cancellation.Err() != nil {
		return nil, s.reject("workspace immutable data unavailable")
	}
	data := bytes.Clone(s.data)
	if s.cancellation.Err() != nil {
		return nil, s.reject("workspace cancelled before copy")
	}
	s.state = 4
	return data, nil
}

// One dedicated data reader must physically end. Cancellation of a blocking
// native pipe requires the future actual owned-I/O adapter; no abandoned waiter
// or Go boolean is native whole-VM authority.
func (s *workspaceStream) readAll(reader io.Reader, chunk func([]byte) error) error {
	if reader == nil {
		return s.reject("workspace reader unavailable")
	}
	for s.state == 1 {
		if s.cancellation.Err() != nil {
			return s.reject("workspace stream cancelled")
		}
		var header [workspaceHeader]byte
		if _, err := io.ReadFull(reader, header[:]); err != nil {
			return s.reject("workspace truncated header")
		}
		n := binary.LittleEndian.Uint32(header[32:36])
		if n > workspaceChunk || s.framed+workspaceHeader+int(n) > workspaceFramedMaximum {
			return s.reject("workspace allocation bound rejected")
		}
		frame := make([]byte, workspaceHeader+int(n))
		copy(frame, header[:])
		if _, err := io.ReadFull(reader, frame[workspaceHeader:]); err != nil {
			return s.reject("workspace truncated body")
		}
		data, err := s.accept(frame)
		if err != nil {
			return err
		}
		if len(data) > 0 && chunk != nil {
			if err = chunk(data); err != nil {
				return s.reject("workspace owned-file chunk write failed")
			}
		}
	}
	var extra [1]byte
	n, err := reader.Read(extra[:])
	if n != 0 || err != io.EOF {
		return s.reject("workspace trailing or missing EOF")
	}
	return s.eof()
}
func workspaceEncode(m workspaceStreamManifest, data []byte) ([]byte, error) {
	if !m.valid() || uint64(len(data)) != m.total || sha256.Sum256(data) != m.digest {
		return nil, errors.New("workspace source data rejected")
	}
	result := make([]byte, 0, len(data)+33*workspaceHeader)
	offset := 0
	sequence := uint32(0)
	for {
		n := len(data) - offset
		if n > workspaceChunk {
			n = workspaceChunk
		}
		final := offset == len(data)
		frame := make([]byte, workspaceHeader+n)
		copy(frame, []byte("CTMWIO02"))
		frame[8] = m.direction
		if final {
			frame[9] = 1
		}
		binary.LittleEndian.PutUint32(frame[12:16], sequence)
		binary.LittleEndian.PutUint64(frame[16:24], uint64(offset))
		binary.LittleEndian.PutUint64(frame[24:32], m.total)
		binary.LittleEndian.PutUint32(frame[32:36], uint32(n))
		copy(frame[40:72], m.binding[:])
		copy(frame[workspaceHeader:], data[offset:offset+n])
		result = append(result, frame...)
		if final {
			break
		}
		offset += n
		sequence++
	}
	return result, nil
}
