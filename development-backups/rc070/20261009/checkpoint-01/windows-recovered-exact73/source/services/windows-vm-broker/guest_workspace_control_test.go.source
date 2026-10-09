package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"strings"
	"testing"
)

func TestActualGuestMainSelectsExplicitWorkspaceMode(t *testing.T) {
	mode, err := selectGuestMode([]string{"--guest-workspace"})
	if err != nil || mode != guestWorkspaceMode {
		t.Fatalf("actual GuestMain selector rejected explicit workspace mode: %v", err)
	}
}

func validGuestControl(t *testing.T) (workspaceGuestControl, []byte) {
	t.Helper()
	command := "[Console]::WriteLine('bounded-output')"
	digest := sha256.Sum256([]byte(command))
	data := []byte("input canary")
	inputHash := sha256.Sum256(data)
	c := workspaceGuestControl{Version: 2, Source: strings.Repeat("a", 40), Session: "58cb51d5-b4bb-4a81-88c2-d9a239bcb04d", Operation: "2d59f83a-11da-4164-b770-d071b83d0cf4", Binding: strings.Repeat("b", 64), InputSHA256: hex.EncodeToString(inputHash[:]), CommandSHA256: hex.EncodeToString(digest[:]), InputBytes: uint64(len(data)), InputLeaf: "input.bin", OutputLeaf: "output.bin", Command: command, Stdin: "", TimeoutMS: 30000}
	raw, e := json.Marshal(c)
	if e != nil {
		t.Fatal(e)
	}
	return c, raw
}
func frameGuestControl(raw []byte) []byte {
	wire := make([]byte, 4+len(raw))
	binary.LittleEndian.PutUint32(wire[:4], uint32(len(raw)))
	copy(wire[4:], raw)
	return wire
}
func TestGuestWorkspaceModeCompatibilityAndExtraArgumentsReject(t *testing.T) {
	mode, e := selectGuestMode([]string{"--guest"})
	if e != nil || mode != guestFixtureMode {
		t.Fatal("old fixture changed")
	}
	for _, args := range [][]string{nil, {"guest"}, {"--guest", "extra"}, {"--guest-workspace", "--child"}, {"--child"}} {
		if _, e = selectGuestMode(args); e == nil {
			t.Fatal("mode accepted extra/unknown", args)
		}
	}
}
func TestGuestWorkspaceControlExactBytesAndStreamBoundary(t *testing.T) {
	c, raw := validGuestControl(t)
	got, digest, e := parseWorkspaceGuestControl(raw, c.Source)
	if e != nil || got != c || digest != sha256.Sum256(raw) {
		t.Fatal("control binding", e)
	}
	data := []byte("input canary")
	wire, e := workspaceEncode(c.inputManifest(), data)
	if e != nil {
		t.Fatal(e)
	}
	r := bytes.NewReader(append(frameGuestControl(raw), wire...))
	got, _, e = readWorkspaceGuestControl(r, c.Source)
	if e != nil || got != c {
		t.Fatal("physical header", e)
	}
	s, e := newWorkspaceStream(context.Background(), got.inputManifest())
	if e != nil || s.readAll(r, nil) != nil {
		t.Fatal("exact dedicated input boundary", e)
	}
	actual, e := s.dataCopy()
	if e != nil || !bytes.Equal(actual, data) {
		t.Fatal("same data", e)
	}
	spaced := append([]byte(" \n"), raw...)
	_, other, e := parseWorkspaceGuestControl(spaced, c.Source)
	if e != nil || other == digest {
		t.Fatal("control raw bytes normalized")
	}
}
func TestGuestWorkspaceControlDuplicateUnknownNullTypeUTF8AndSurrogatesReject(t *testing.T) {
	c, raw := validGuestControl(t)
	cases := map[string][]byte{"duplicate": append([]byte(`{"version":2,`), raw[1:]...), "unknown": append([]byte(`{"approve":true,`), raw[1:]...), "case-key": bytes.Replace(raw, []byte(`"source"`), []byte(`"Source"`), 1), "null": bytes.Replace(raw, []byte(`"input_bytes":12`), []byte(`"input_bytes":null`), 1), "bool": bytes.Replace(raw, []byte(`"input_bytes":12`), []byte(`"input_bytes":true`), 1), "fraction": bytes.Replace(raw, []byte(`"input_bytes":12`), []byte(`"input_bytes":12.0`), 1), "utf8": append(bytes.Clone(raw), 0xff), "high-surrogate": bytes.Replace(raw, []byte(`"stdin":""`), []byte(`"stdin":"\uD800"`), 1), "low-surrogate": bytes.Replace(raw, []byte(`"stdin":""`), []byte(`"stdin":"\uDC00"`), 1), "trailing": append(bytes.Clone(raw), []byte(` {}`)...), "missing": bytes.Replace(raw, []byte(`"stdin":"",`), nil, 1)}
	for name, bad := range cases {
		t.Run(name, func(t *testing.T) {
			if _, _, e := parseWorkspaceGuestControl(bad, c.Source); e == nil {
				t.Fatal("invalid control accepted")
			}
		})
	}
}
func TestGuestWorkspaceControlIdentityLeafAndCommandHashReject(t *testing.T) {
	base, _ := validGuestControl(t)
	cases := map[string]func(*workspaceGuestControl){"source": func(c *workspaceGuestControl) { c.Source = strings.Repeat("c", 40) }, "zero-source": func(c *workspaceGuestControl) { c.Source = strings.Repeat("0", 40) }, "session": func(c *workspaceGuestControl) { c.Session = "58cb51d5-b4bb-3a81-88c2-d9a239bcb04d" }, "operation": func(c *workspaceGuestControl) { c.Operation = "../operation" }, "zero-binding": func(c *workspaceGuestControl) { c.Binding = strings.Repeat("0", 64) }, "upper-hash": func(c *workspaceGuestControl) { c.Binding = strings.Repeat("B", 64) }, "digest": func(c *workspaceGuestControl) { c.CommandSHA256 = strings.Repeat("0", 64) }, "input-name": func(c *workspaceGuestControl) { c.InputLeaf = "nested/input.bin" }, "absolute": func(c *workspaceGuestControl) { c.InputLeaf = `C:\input.bin` }, "ads": func(c *workspaceGuestControl) { c.OutputLeaf = "out:ads" }, "device": func(c *workspaceGuestControl) { c.OutputLeaf = "NUL.txt" }, "alias": func(c *workspaceGuestControl) { c.OutputLeaf = "INPUT.BIN" }, "unicode": func(c *workspaceGuestControl) { c.InputLeaf = "输入.bin" }, "long-leaf": func(c *workspaceGuestControl) { c.OutputLeaf = strings.Repeat("a", 121) }}
	for name, change := range cases {
		t.Run(name, func(t *testing.T) {
			c := base
			change(&c)
			raw, _ := json.Marshal(c)
			if _, _, e := parseWorkspaceGuestControl(raw, base.Source); e == nil {
				t.Fatal("invalid identity/path/hash accepted")
			}
		})
	}
}
func TestGuestWorkspaceControlFiniteBudgetsAndTruncationReject(t *testing.T) {
	base, raw := validGuestControl(t)
	for name, change := range map[string]func(*workspaceGuestControl){"cmd": func(c *workspaceGuestControl) { c.Command = strings.Repeat("a", 2049) }, "stdin": func(c *workspaceGuestControl) { c.Stdin = strings.Repeat("a", 1025) }, "bytes": func(c *workspaceGuestControl) { c.InputBytes = workspaceMaximum + 1 }, "timeout-zero": func(c *workspaceGuestControl) { c.TimeoutMS = 0 }, "timeout": func(c *workspaceGuestControl) { c.TimeoutMS = 30001 }} {
		t.Run(name, func(t *testing.T) {
			c := base
			change(&c)
			hash := sha256.Sum256([]byte(c.Command))
			c.CommandSHA256 = hex.EncodeToString(hash[:])
			bad, _ := json.Marshal(c)
			if _, _, e := parseWorkspaceGuestControl(bad, base.Source); e == nil {
				t.Fatal("bound accepted")
			}
		})
	}
	for name, bad := range map[string][]byte{"short-header": {1, 0}, "zero-size": {0, 0, 0, 0}, "oversize": {1, 16, 0, 0}, "short-body": frameGuestControl(raw)[:len(raw)]} {
		t.Run(name, func(t *testing.T) {
			if _, _, e := readWorkspaceGuestControl(bytes.NewReader(bad), base.Source); e == nil {
				t.Fatal("truncated/oversized accepted")
			}
		})
	}
	c := base
	c.Command = strings.Repeat("a", 2048)
	c.Stdin = strings.Repeat("b", 1024)
	hash := sha256.Sum256([]byte(c.Command))
	c.CommandSHA256 = hex.EncodeToString(hash[:])
	good, _ := json.Marshal(c)
	if _, _, e := parseWorkspaceGuestControl(good, base.Source); e != nil {
		t.Fatal("exact argument bounds rejected", e)
	}
	if _, _, e := parseWorkspaceGuestControl(bytes.Repeat([]byte(" "), guestWorkspaceControlMaximum+1), base.Source); e == nil {
		t.Fatal("raw JSON allocation bound")
	}
}
