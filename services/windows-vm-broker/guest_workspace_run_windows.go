//go:build windows && guest

package main

import (
	"context"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"os"
	"os/exec"
	"strings"
	"sync"
	"syscall"
	"time"
)

// No native grant/VM/system/retirement/issuer is constructed or deserialized here.
type guestWorkspaceRun struct {
	realm                                                                              guestRealmRoot
	ctx                                                                                context.Context
	cancel                                                                             context.CancelFunc
	control                                                                            workspaceGuestControl
	controlHash                                                                        [32]byte
	base, parentRaw                                                                    syscall.Handle
	parent                                                                             *os.File
	parentID                                                                           guestFileIdentity
	input                                                                              *guestOwnedFile
	output                                                                             *guestOwnedOutput
	command                                                                            *exec.Cmd
	inputBytes, outputWire, metadata                                                   []byte
	path                                                                               string
	createMayHaveEffect, uncertain, sourcesClosed, commandJoined, commandMayHaveEffect bool
	commandResourcesUnconfirmed, publicationConsumed                                   bool
}

// Guest-realm data provider only; not a host root permission. Production GuestMain
// always supplies the fixed guest workspace. Only native CI tests supply a temp root.
type guestRealmRoot struct{ path string }

var guestRunHeld = struct {
	sync.Mutex
	entries map[*guestWorkspaceRun]bool
}{entries: make(map[*guestWorkspaceRun]bool)}

func registerGuestRun(r *guestWorkspaceRun) error {
	guestRunHeld.Lock()
	defer guestRunHeld.Unlock()
	if len(guestRunHeld.entries) >= 256 {
		return errors.New("guest run ownership census full")
	}
	guestRunHeld.entries[r] = true
	return nil
}
func (r *guestWorkspaceRun) markRunPanic() {
	if p := recover(); p != nil {
		r.uncertain = true
		panic(p)
	}
}
func (r *guestWorkspaceRun) releaseKnown() {
	r.cancel()
	if !guestRunCanDiscard(r.createMayHaveEffect, r.commandMayHaveEffect) {
		// File close is not directory disposition. Keep the entire owner after
		// possible creation, including a malformed input before command Start.
		if r.commandMayHaveEffect {
			// Cmd.Wait also ignores some internal pipe Close results.
			r.commandResourcesUnconfirmed = true
		}
		return
	}
	r.inputBytes = nil
	r.outputWire = nil
	r.metadata = nil
	r.command = nil
	guestRunHeld.Lock()
	delete(guestRunHeld.entries, r)
	guestRunHeld.Unlock()
}

type guestCommandOutput struct {
	run    *guestWorkspaceRun
	offset uint64
	mu     sync.Mutex
}

func (w *guestCommandOutput) Write(data []byte) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	r := w.run
	if r.ctx.Err() != nil || r.output == nil || r.output.poisoned || uint64(len(data)) > workspaceMaximum-w.offset {
		return 0, errors.New("guest command output bound or cancellation")
	}
	written := 0
	for written < len(data) {
		n := len(data) - written
		if n > workspaceChunk {
			n = workspaceChunk
		}
		info, e := r.output.checkPin()
		if e != nil || info.size != w.offset {
			return written, errors.New("guest command output identity or cursor conflict")
		}
		pos, e := syscall.Seek(r.output.writer, 0, 1)
		if e != nil || pos < 0 || uint64(pos) != w.offset || r.ctx.Err() != nil {
			return written, errors.New("guest command writer position rejected")
		}
		var count uint32
		e = syscall.WriteFile(r.output.writer, data[written:written+n], &count, nil)
		if e != nil || int(count) != n {
			r.output.poisoned = true
			return written, errors.New("guest command partial output write")
		}
		written += n
		w.offset += uint64(n)
		info, e = r.output.checkPin()
		if e != nil || info.size != w.offset || r.ctx.Err() != nil {
			return written, errors.New("guest command output changed or cancelled")
		}
	}
	return written, nil
}

type guestCommandStderr struct {
	bytes    []byte
	overflow bool
}

func (w *guestCommandStderr) Write(data []byte) (int, error) {
	if len(data) > guestWorkspaceStderrMaximum-len(w.bytes) {
		w.overflow = true
		return 0, errors.New("guest command stderr limit")
	}
	w.bytes = append(w.bytes, data...)
	return len(data), nil
}

func guestEvidenceJSON(e guestInputEvidence) any {
	return map[string]any{"volume": e.identity.volume, "file_id": hex.EncodeToString(e.identity.id[:]), "parent_volume": e.parent.volume, "parent_file_id": hex.EncodeToString(e.parent.id[:]), "binding": hex.EncodeToString(e.binding[:]), "bytes": e.size, "sha256": hex.EncodeToString(e.digest[:])}
}

// Actual private GuestMain producer. Success is bounded DATA only, never exit of
// the VM/descendants or authority for a native host output. CommandContext/Wait
// joins this command's stdin/stdout/stderr copying; future wholeVM owner remains
// responsible for all descendant/process/pipe/HCS retirement.
func executeGuestWorkspace(reader io.Reader, source string, realm guestRealmRoot) (r *guestWorkspaceRun, err error) {
	control, controlHash, e := readWorkspaceGuestControl(reader, source)
	if e != nil {
		return nil, e
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(control.TimeoutMS)*time.Millisecond)
	r = &guestWorkspaceRun{ctx: ctx, cancel: cancel, control: control, controlHash: controlHash, realm: realm}
	if e = registerGuestRun(r); e != nil {
		cancel()
		return nil, e
	}
	success := false
	defer func() {
		// Mark uncertainty BEFORE cleanup; an unwind must not release the whole
		// registered object even if some file handles could have closed normally.
		if p := recover(); p != nil {
			r.uncertain = true
			cancel()
			panic(p)
		}
		if !success {
			cancel()
			if r.commandMayHaveEffect && !r.commandJoined {
				r.uncertain = true
			}
			if r.closeSources() == nil {
				r.releaseKnown()
			}
		}
	}()
	if e = r.openRoot(); e != nil {
		return r, e
	}
	r.input, _, e = receiveGuestWorkspaceInput(ctx, r.parent, r.parentID, control.InputLeaf, control.inputManifest(), reader)
	if e != nil {
		return r, e
	}
	r.inputBytes = append([]byte(nil), r.input.immutable...)
	if e = r.input.freezeForWorkload(); e != nil {
		return r, e
	}
	r.output, e = createGuestWorkspaceOutput(ctx, r.parent, r.parentID, control.OutputLeaf, r.input)
	if e != nil {
		return r, e
	}
	stdout := &guestCommandOutput{run: r}
	stderr := &guestCommandStderr{}
	r.command = exec.CommandContext(ctx, powershell)
	r.command.SysProcAttr = &syscall.SysProcAttr{CmdLine: encodedCommand(control.Command)}
	r.command.Dir = r.path
	r.command.Stdin = strings.NewReader(control.Stdin)
	r.command.Stdout = stdout
	r.command.Stderr = stderr
	r.command.WaitDelay = 2 * time.Second
	r.commandMayHaveEffect = true
	r.commandResourcesUnconfirmed = true
	if e = r.command.Start(); e != nil {
		r.uncertain = true
		return r, errors.New("guest command start failed")
	}
	e = r.command.Wait()
	r.commandJoined = e == nil && r.command.ProcessState != nil
	if e != nil || ctx.Err() != nil || stderr.overflow || r.command.ProcessState == nil || r.command.ProcessState.ExitCode() != 0 {
		r.uncertain = true
		return r, errors.New("guest command exit or IO failed")
	}
	if _, e = r.output.freeze(); e != nil {
		return r, e
	}
	evidence, wire, e := r.output.wire()
	if e != nil || ctx.Err() != nil {
		return r, errors.New("guest output data unavailable")
	}
	r.outputWire = wire
	r.metadata, e = json.Marshal(map[string]any{"version": 2, "source": control.Source, "session": control.Session, "operation": control.Operation, "control_sha256": hex.EncodeToString(controlHash[:]), "command_sha256": control.CommandSHA256, "input": guestEvidenceJSON(evidence.input), "output": guestEvidenceJSON(evidence.output), "exit_code": 0, "data_only": true, "command_resources_unconfirmed": true})
	if e != nil || len(r.metadata) > guestWorkspaceControlMaximum || ctx.Err() != nil {
		return r, errors.New("guest output metadata unavailable")
	}
	if e = r.closeSources(); e != nil {
		return r, e
	}
	if ctx.Err() != nil {
		return r, errors.New("guest cancelled before publication")
	}
	success = true
	return r, nil
}
func publishGuestWorkspace(r *guestWorkspaceRun, writer io.Writer) error {
	if r == nil || writer == nil || !r.sourcesClosed || r.uncertain || r.publicationConsumed || !r.commandJoined || len(r.metadata) == 0 || len(r.metadata) > guestWorkspaceControlMaximum || len(r.outputWire) > workspaceFramedMaximum {
		return errors.New("guest publication unavailable")
	}
	defer r.markRunPanic()
	r.publicationConsumed = true
	var head [4]byte
	binary.LittleEndian.PutUint32(head[:], uint32(len(r.metadata)))
	// Short writes are failure. Do not discard whole data owner on unknown publish.
	for _, data := range [][]byte{head[:], r.metadata, r.outputWire} {
		if r.ctx.Err() != nil {
			r.uncertain = true
			r.cancel()
			return errors.New("guest publication cancelled")
		}
		n, e := writer.Write(data)
		if e != nil || n != len(data) {
			r.uncertain = true
			r.cancel()
			return errors.New("guest output publication failed")
		}
		if r.ctx.Err() != nil {
			r.uncertain = true
			r.cancel()
			return errors.New("guest publication cancelled after write")
		}
	}
	r.releaseKnown()
	return nil
}
func runGuestWorkspace() error {
	r, e := executeGuestWorkspace(os.Stdin, buildSource, guestRealmRoot{path: workspace})
	if e != nil {
		return e
	}
	return publishGuestWorkspace(r, os.Stdout)
}
