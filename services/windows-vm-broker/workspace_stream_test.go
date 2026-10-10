package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"strconv"
	"testing"
)

func streamManifest(data []byte) workspaceStreamManifest {
	b, _ := hex.DecodeString("0e5501c158783b48e1792eb9d393e00ec04d2c8585c71fc7800d8c08d7413bd2")
	var binding [32]byte
	copy(binding[:], b)
	return workspaceStreamManifest{binding: binding, direction: 1, total: uint64(len(data)), digest: sha256.Sum256(data)}
}
func TestWorkspaceRustGoCanonicalVector(t *testing.T) {
	data := []byte("input canary")
	m := streamManifest(data)
	wire, e := workspaceEncode(m, data)
	if e != nil {
		t.Fatal(e)
	}
	expected := "43544d57494f3032010000000000000000000000000000000c000000000000000c000000000000000e5501c158783b48e1792eb9d393e00ec04d2c8585c71fc7800d8c08d7413bd2696e7075742063616e617279" +
		"43544d57494f303201010000010000000c000000000000000c0000000000000000000000000000000e5501c158783b48e1792eb9d393e00ec04d2c8585c71fc7800d8c08d7413bd2"
	if hex.EncodeToString(wire) != expected {
		t.Fatal("Rust/Go schema vector mismatch")
	}
	s, e := newWorkspaceStream(context.Background(), m)
	if e != nil {
		t.Fatal(e)
	}
	if e = s.readAll(bytes.NewReader(wire), nil); e != nil {
		t.Fatal(e)
	}
	got, e := s.dataCopy()
	if e != nil || !bytes.Equal(got, data) {
		t.Fatal("copy", e)
	}
	got[0] ^= 1
	if bytes.Equal(got, s.data) {
		t.Fatal("aliased input")
	}
	if _, e = s.dataCopy(); e == nil {
		t.Fatal("second consumption")
	}
}
func TestWorkspaceExactZeroAndOneMiBBudgets(t *testing.T) {
	for _, size := range []int{0, 1, workspaceChunk - 1, workspaceChunk, workspaceChunk + 1, workspaceMaximum} {
		t.Run(strconv.Itoa(size), func(t *testing.T) {
			data := bytes.Repeat([]byte{7}, size)
			m := streamManifest(data)
			wire, e := workspaceEncode(m, data)
			if e != nil {
				t.Fatal(e)
			}
			if len(wire) > workspaceFramedMaximum {
				t.Fatal("budget")
			}
			if size == workspaceMaximum && len(wire) != workspaceFramedMaximum {
				t.Fatal("full bound")
			}
			s, _ := newWorkspaceStream(context.Background(), m)
			if e = s.readAll(bytes.NewReader(wire), nil); e != nil {
				t.Fatal(e)
			}
			got, e := s.dataCopy()
			if e != nil || !bytes.Equal(got, data) {
				t.Fatal("bytes", e)
			}
		})
	}
	m := streamManifest(make([]byte, workspaceMaximum+1))
	if _, e := workspaceEncode(m, make([]byte, workspaceMaximum+1)); e == nil {
		t.Fatal("overflow")
	}
}
func TestWorkspaceEveryHeaderDimensionPermanentlyPoisons(t *testing.T) {
	data := []byte("input canary")
	m := streamManifest(data)
	wire, _ := workspaceEncode(m, data)
	for _, pos := range []int{0, 8, 9, 10, 11, 12, 16, 24, 32, 36, 40, 71} {
		t.Run(strconv.Itoa(pos), func(t *testing.T) {
			bad := bytes.Clone(wire)
			bad[pos] ^= 0x80
			s, _ := newWorkspaceStream(context.Background(), m)
			if e := s.readAll(bytes.NewReader(bad), nil); e == nil {
				t.Fatal("dimension accepted", pos)
			}
			if _, e := s.dataCopy(); e == nil {
				t.Fatal("poison reopened")
			}
			if e := s.readAll(bytes.NewReader(wire), nil); e == nil {
				t.Fatal("reset")
			}
		})
	}
}
func TestWorkspaceTruncationTrailingReplayAndFinalDigestReject(t *testing.T) {
	data := []byte("input canary")
	m := streamManifest(data)
	wire, _ := workspaceEncode(m, data)
	replay := append(bytes.Clone(wire[:84]), wire...)
	for name, bad := range map[string][]byte{"short-header": wire[:71], "short-body": wire[:80], "no-eof": wire[:84], "short-eof": wire[:len(wire)-1], "trailing": append(bytes.Clone(wire), 0), "replay": replay} {
		t.Run(name, func(t *testing.T) {
			s, _ := newWorkspaceStream(context.Background(), m)
			if e := s.readAll(bytes.NewReader(bad), nil); e == nil {
				t.Fatal("accepted")
			}
		})
	}
	m.digest[31] ^= 1
	s, _ := newWorkspaceStream(context.Background(), m)
	if e := s.readAll(bytes.NewReader(wire), nil); e == nil {
		t.Fatal("hash")
	}
}
func TestWorkspaceAllocationBoundCancellationAndChunkFailure(t *testing.T) {
	data := bytes.Repeat([]byte{2}, workspaceChunk+1)
	m := streamManifest(data)
	wire, _ := workspaceEncode(m, data)
	bad := bytes.Clone(wire[:workspaceHeader])
	binary.LittleEndian.PutUint32(bad[32:36], workspaceChunk+1)
	s, _ := newWorkspaceStream(context.Background(), m)
	if e := s.readAll(bytes.NewReader(bad), nil); e == nil {
		t.Fatal("allocation")
	}
	ctx, cancel := context.WithCancel(context.Background())
	s, _ = newWorkspaceStream(ctx, m)
	cancel()
	if e := s.readAll(bytes.NewReader(wire), nil); e == nil {
		t.Fatal("cancel")
	}
	ctx, cancel = context.WithCancel(context.Background())
	s, _ = newWorkspaceStream(ctx, m)
	if e := s.readAll(bytes.NewReader(wire), func([]byte) error { cancel(); return nil }); e == nil {
		t.Fatal("between chunks cancellation")
	}
	if _, e := s.dataCopy(); e == nil {
		t.Fatal("cancelled bytes")
	}
}
func TestWorkspaceInputOutputDirectionAndMissingTrustedManifestReject(t *testing.T) {
	data := []byte("output")
	m := streamManifest(data)
	m.direction = 2
	wire, _ := workspaceEncode(m, data)
	s, _ := newWorkspaceStream(context.Background(), m)
	if e := s.readAll(bytes.NewReader(wire), nil); e != nil {
		t.Fatal(e)
	}
	m.direction = 1
	s, _ = newWorkspaceStream(context.Background(), m)
	if e := s.readAll(bytes.NewReader(wire), nil); e == nil {
		t.Fatal("direction")
	}
	if _, e := newWorkspaceStream(nil, m); e == nil {
		t.Fatal("nil cancel")
	}
	m.binding = [32]byte{}
	if _, e := newWorkspaceStream(context.Background(), m); e == nil {
		t.Fatal("unbound")
	}
}
func TestWorkspaceConcurrentCancellationWhileDecoderCallbackIsBlocked(t *testing.T) {
	data := bytes.Repeat([]byte{4}, workspaceChunk+1)
	m := streamManifest(data)
	wire, _ := workspaceEncode(m, data)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	s, _ := newWorkspaceStream(ctx, m)
	entered, release, result := make(chan struct{}), make(chan struct{}), make(chan error, 1)
	go func() {
		result <- s.readAll(bytes.NewReader(wire), func([]byte) error {
			close(entered)
			<-release
			return nil
		})
	}()
	<-entered
	cancel()
	close(release)
	if e := <-result; e == nil {
		t.Fatal("concurrent cancellation ignored")
	}
	if _, e := s.dataCopy(); e == nil {
		t.Fatal("cancelled detached data accepted")
	}
}
