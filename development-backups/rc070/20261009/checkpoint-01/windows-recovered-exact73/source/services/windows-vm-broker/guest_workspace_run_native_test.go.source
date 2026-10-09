//go:build windows && guest

package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
)

// Only future explicitly selected native GitHub CI runs these tests. Fixture
// paths and wire identities remain DATA; they cannot issue host permissions.
// Uncertain owners are deliberately not force-closed or deleted by cleanup.
func actualGuestRunnerRoot(t *testing.T) string {
	t.Helper()
	if os.Getenv("GITHUB_ACTIONS") != "true" || os.Getenv("RUNNER_OS") != "Windows" || os.Getenv("CTM_GUEST_FILE_NATIVE_ENABLE") != "OWNED_TEMP_FIXTURE_ONLY" || buildSource != os.Getenv("GITHUB_SHA") || !guestControlHex(buildSource, 40) || buildSource == strings.Repeat("0", 40) {
		t.Fatal("actual candidate-bound Windows runner fixture required")
	}
	base, e := filepath.Abs(os.Getenv("CTM_GUEST_FILE_NATIVE_ROOT"))
	runner, x := filepath.Abs(os.Getenv("RUNNER_TEMP"))
	rel, y := filepath.Rel(runner, base)
	if e != nil || x != nil || y != nil || os.Getenv("RUNNER_TEMP") == "" || os.Getenv("CTM_GUEST_FILE_NATIVE_ROOT") == "" || rel == "." || rel == ".." || strings.HasPrefix(rel, ".."+string(os.PathSeparator)) || filepath.IsAbs(rel) {
		t.Fatal("fixture must be a dedicated directory below RUNNER_TEMP")
	}
	root, e := os.MkdirTemp(base, "actual-guest-workspace-")
	if e != nil {
		t.Fatal(e)
	}
	t.Log("owned runner fixture; unknown handles survive until disposable job teardown:", root)
	return root
}
func actualGuestControl(t *testing.T, command string) workspaceGuestControl {
	t.Helper()
	c, _ := validGuestControl(t)
	c.Source, c.Command = buildSource, command
	digest := sha256.Sum256([]byte(command))
	c.CommandSHA256 = hex.EncodeToString(digest[:])
	return c
}
func actualGuestRequest(t *testing.T, c workspaceGuestControl) []byte {
	t.Helper()
	raw, e := json.Marshal(c)
	if e != nil {
		t.Fatal(e)
	}
	wire, e := workspaceEncode(c.inputManifest(), []byte("input canary"))
	if e != nil {
		t.Fatal(e)
	}
	return append(frameGuestControl(raw), wire...)
}
func actualGuestSuccessfulRun(t *testing.T) (*guestWorkspaceRun, string) {
	t.Helper()
	root := actualGuestRunnerRoot(t)
	c := actualGuestControl(t, "[Console]::OpenStandardOutput().Write([IO.File]::ReadAllBytes('input.bin'),0,12)")
	r, e := executeGuestWorkspace(bytes.NewReader(actualGuestRequest(t, c)), buildSource, guestRealmRoot{path: root})
	if e != nil {
		t.Fatal("actual command execution failed", e)
	}
	return r, root
}
func guestRunIsHeld(r *guestWorkspaceRun) bool {
	guestRunHeld.Lock()
	defer guestRunHeld.Unlock()
	return guestRunHeld.entries[r]
}
func actualGuestPrepareFiles(t *testing.T) (*guestWorkspaceRun, string) {
	t.Helper()
	root := actualGuestRunnerRoot(t)
	c := actualGuestControl(t, "[Console]::Write('not-started')")
	ctx, cancel := context.WithCancel(context.Background())
	r := &guestWorkspaceRun{ctx: ctx, cancel: cancel, control: c, realm: guestRealmRoot{path: root}}
	if e := registerGuestRun(r); e != nil {
		t.Fatal(e)
	}
	if e := r.openRoot(); e != nil {
		t.Fatal(e)
	}
	wire, e := workspaceEncode(c.inputManifest(), []byte("input canary"))
	if e != nil {
		t.Fatal(e)
	}
	r.input, _, e = receiveGuestWorkspaceInput(ctx, r.parent, r.parentID, c.InputLeaf, c.inputManifest(), bytes.NewReader(wire))
	if e != nil {
		t.Fatal(e)
	}
	r.inputBytes = bytes.Clone(r.input.immutable)
	if e = r.input.freezeForWorkload(); e != nil {
		t.Fatal(e)
	}
	r.output, e = createGuestWorkspaceOutput(ctx, r.parent, r.parentID, c.OutputLeaf, r.input)
	if e != nil {
		t.Fatal(e)
	}
	return r, root
}

func TestNativeActualGuestWorkspaceCommandProducesFullFIDHashAndCheckedPublication(t *testing.T) {
	r, root := actualGuestSuccessfulRun(t)
	if !r.sourcesClosed || !r.commandJoined || r.uncertain || r.command == nil || r.command.ProcessState == nil || r.command.ProcessState.ExitCode() != 0 || r.base != 0 || r.parentRaw != 0 || !guestRunIsHeld(r) || !bytes.Equal(r.inputBytes, []byte("input canary")) {
		t.Fatal("actual command/checked source ownership missing")
	}
	var metadata map[string]json.RawMessage
	if e := json.Unmarshal(r.metadata, &metadata); e != nil || string(metadata["data_only"]) != "true" || string(metadata["source"]) != `"`+buildSource+`"` {
		t.Fatal("actual source-bound DATA metadata", e)
	}
	if r.input.identity.id == ([16]byte{}) || r.output.identity.id == ([16]byte{}) || r.output.identity == r.input.identity || r.output.identity.volume != r.input.identity.volume || r.output.parentID != r.parentID {
		t.Fatal("actual independent full file IDs missing")
	}
	var published bytes.Buffer
	if e := publishGuestWorkspace(r, &published); e != nil {
		t.Fatal(e)
	}
	raw := published.Bytes()
	n := int(binary.LittleEndian.Uint32(raw[:4]))
	if n <= 0 || n > guestWorkspaceControlMaximum || 4+n > len(raw) {
		t.Fatal("publication framing")
	}
	m := r.control.inputManifest()
	m.direction = 2
	s, e := newWorkspaceStream(context.Background(), m)
	if e != nil || s.readAll(bytes.NewReader(raw[4+n:]), nil) != nil {
		t.Fatal("actual output stream rejected", e)
	}
	data, e := s.dataCopy()
	if e != nil || !bytes.Equal(data, []byte("input canary")) || !guestRunIsHeld(r) || !r.commandResourcesUnconfirmed || !r.publicationConsumed || r.inputBytes == nil || r.outputWire == nil || r.command == nil {
		t.Fatal("single use DATA publication discarded unconfirmed command owner", e)
	}
	if e = publishGuestWorkspace(r, &published); e == nil {
		t.Fatal("publication replay")
	}
	if e = os.RemoveAll(root); e != nil {
		t.Fatal("all known native handles must have closed", e)
	}
}
func TestNativeActualGuestInputReadonlyFreezeAllowsRuntimeReadButDeniesWrite(t *testing.T) {
	r, root := actualGuestPrepareFiles(t)
	if !r.input.workloadReadOnly || r.input.workloadPin == 0 || r.input.handle == 0 || r.input.workloadPin == r.input.handle {
		t.Fatal("actual independent readonly handles absent")
	}
	data, e := os.ReadFile(filepath.Join(r.path, r.control.InputLeaf))
	if e != nil || !bytes.Equal(data, r.inputBytes) {
		t.Fatal("ordinary runtime read incompatible with actual freeze", e)
	}
	if w, e := os.OpenFile(filepath.Join(r.path, r.control.InputLeaf), os.O_WRONLY, 0); e == nil {
		_ = w.Close()
		t.Fatal("readonly input admitted writer")
	}
	if e = r.input.writeChunk([]byte("x")); e == nil {
		t.Fatal("original writer API accepted readonly mode")
	}
	if e = r.closeSources(); e != nil {
		t.Fatal(e)
	}
	r.releaseKnown()
	if e = os.RemoveAll(root); e != nil {
		t.Fatal(e)
	}
}
func TestNativeActualGuestExistingOperationDirectoryNeverReuses(t *testing.T) {
	root := actualGuestRunnerRoot(t)
	c := actualGuestControl(t, "[Console]::Write('not-started')")
	op := filepath.Join(root, "ctm-workspace-"+strings.ReplaceAll(c.Operation, "-", ""))
	if e := os.Mkdir(op, 0700); e != nil {
		t.Fatal(e)
	}
	canary := filepath.Join(op, "existing.bin")
	if e := os.WriteFile(canary, []byte("existing"), 0600); e != nil {
		t.Fatal(e)
	}
	r, e := executeGuestWorkspace(bytes.NewReader(actualGuestRequest(t, c)), buildSource, guestRealmRoot{path: root})
	if e == nil || r == nil || !r.uncertain || r.command != nil || !guestRunIsHeld(r) || r.base == 0 {
		t.Fatal("operation directory was reused or uncertainty discarded")
	}
	data, e := os.ReadFile(canary)
	if e != nil || string(data) != "existing" {
		t.Fatal("existing operation modified", e)
	}
}
func TestNativeActualGuestMalformedInputNeverStartsCommand(t *testing.T) {
	root := actualGuestRunnerRoot(t)
	c := actualGuestControl(t, "[Console]::Write('must-not-run')")
	wire := actualGuestRequest(t, c)
	wire[len(wire)-1] ^= 1
	r, e := executeGuestWorkspace(bytes.NewReader(wire), buildSource, guestRealmRoot{path: root})
	if e == nil || r == nil || r.command != nil || r.output != nil || r.commandMayHaveEffect || len(r.outputWire) != 0 {
		t.Fatal("bad input reached actual command")
	}
	// Explicit migration from the frozen Guest11 unregister expectation:
	// checked file handles do not retire the already-created operation directory.
	if !r.sourcesClosed || !r.createMayHaveEffect || !guestRunIsHeld(r) || r.ctx == nil || r.input == nil || r.path == "" || r.commandResourcesUnconfirmed {
		t.Fatal("bad input lost the concrete created-directory owner")
	}
	if e = os.RemoveAll(root); e != nil {
		t.Fatal(e)
	}
}
func TestNativeActualGuestCommandFailuresRetainWholeRun(t *testing.T) {
	for name, command := range map[string]string{
		"exit":     "exit 7",
		"stdout":   "[Console]::OpenStandardOutput().Write([byte[]]::new(1048577),0,1048577)",
		"stderr":   "[Console]::Error.Write(('x' * 8193))",
		"deadline": "Start-Sleep -Seconds 60",
	} {
		t.Run(name, func(t *testing.T) {
			root := actualGuestRunnerRoot(t)
			c := actualGuestControl(t, command)
			if name == "deadline" {
				c.TimeoutMS = 1000
			}
			r, e := executeGuestWorkspace(bytes.NewReader(actualGuestRequest(t, c)), buildSource, guestRealmRoot{path: root})
			if e == nil || r == nil || !r.uncertain || !r.commandMayHaveEffect || r.command == nil || !guestRunIsHeld(r) || r.base == 0 || r.parent == nil || r.input == nil || r.output == nil || !bytes.Equal(r.inputBytes, []byte("input canary")) || len(r.outputWire) != 0 || r.sourcesClosed {
				t.Fatal("failed real command dropped concrete owner or published data")
			}
		})
	}
}
func TestNativeActualGuestFailedCloseRetainsWholeRunAndActualRawValues(t *testing.T) {
	r, _ := actualGuestPrepareFiles(t)
	w := &guestCommandOutput{run: r}
	if n, e := w.Write([]byte("output canary")); e != nil || n != 13 {
		t.Fatal(e)
	}
	if _, e := r.output.freeze(); e != nil {
		t.Fatal(e)
	}
	_, wire, e := r.output.wire()
	if e != nil {
		t.Fatal(e)
	}
	r.outputWire = wire
	old := r.output.read
	// No intervening native open between this deliberate fault and actual close.
	if e = syscall.CloseHandle(old); e != nil {
		t.Fatal(e)
	}
	if e = r.closeSources(); e == nil || !r.uncertain || !r.output.uncertain || r.output.read != old || r.output.pin == 0 || r.base == 0 || r.parent == nil || r.input.handle == 0 || !guestRunIsHeld(r) || !bytes.Equal(r.inputBytes, []byte("input canary")) || !bytes.Equal(r.output.immutable, []byte("output canary")) || !bytes.Equal(r.outputWire, wire) {
		t.Fatal("failed actual close lost whole registered run/data/raw values")
	}
}

type actualGuestShortWriter struct{}

func (actualGuestShortWriter) Write(b []byte) (int, error) { return len(b) - 1, nil }

type actualGuestCancelWriter struct{ cancel context.CancelFunc }

func (w actualGuestCancelWriter) Write(b []byte) (int, error) { w.cancel(); return len(b), nil }

type actualGuestPanicWriter struct{}

func (actualGuestPanicWriter) Write([]byte) (int, error) { panic("controlled publication unwind") }

func TestNativeActualGuestPublicationShortWriteRetainsWholeDataOwner(t *testing.T) {
	r, _ := actualGuestSuccessfulRun(t)
	wire, metadata := bytes.Clone(r.outputWire), bytes.Clone(r.metadata)
	if e := publishGuestWorkspace(r, actualGuestShortWriter{}); e == nil || !r.uncertain || !guestRunIsHeld(r) || !bytes.Equal(wire, r.outputWire) || !bytes.Equal(metadata, r.metadata) || r.command == nil || r.ctx == nil || r.input == nil || r.output == nil || r.control.Source != buildSource {
		t.Fatal("unknown publication dropped whole owner")
	}
}
func TestNativeActualGuestPublicationLateCancellationRetainsWholeDataOwner(t *testing.T) {
	r, _ := actualGuestSuccessfulRun(t)
	wire := bytes.Clone(r.outputWire)
	if e := publishGuestWorkspace(r, actualGuestCancelWriter{r.cancel}); e == nil || !r.uncertain || !guestRunIsHeld(r) || !bytes.Equal(wire, r.outputWire) || r.command == nil || !errors.Is(r.ctx.Err(), context.Canceled) {
		t.Fatal("late publication cancellation accepted or discarded owner")
	}
}
func TestNativeActualGuestPublicationPanicRetainsWholeDataOwner(t *testing.T) {
	r, _ := actualGuestSuccessfulRun(t)
	wire, metadata := bytes.Clone(r.outputWire), bytes.Clone(r.metadata)
	func() {
		defer func() {
			if recover() == nil {
				t.Fatal("controlled panic missing")
			}
		}()
		_ = publishGuestWorkspace(r, actualGuestPanicWriter{})
	}()
	if !r.uncertain || !guestRunIsHeld(r) || !bytes.Equal(wire, r.outputWire) || !bytes.Equal(metadata, r.metadata) || r.command == nil || r.ctx == nil || r.input == nil || r.output == nil {
		t.Fatal("publication panic lost whole owner")
	}
}
