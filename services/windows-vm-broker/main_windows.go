//go:build windows && !guest

package main

import (
	"context"
	"errors"
	"fmt"
	"github.com/Microsoft/go-winio/pkg/guid"
	"os"
	"path/filepath"
	"time"
)

type controlResult struct {
	request Request
	err     error
}

func runSession(assets string) error {
	read, written := 0, 0
	var prepare Request
	if e := readFrame(os.Stdin, &read, &prepare); e != nil {
		return e
	}
	if e := validateRequest(prepare, buildSource, prepare.Session, 0, "prepare"); e != nil {
		return e
	}
	if e := validateAssets(assets); e != nil {
		return e
	}
	id, e := guid.NewV4()
	if e != nil {
		return e
	}
	v := &ownedVM{id: id.String(), assets: assets, root: filepath.Join(assets, "session-"+prepare.Session), receipt: Cleanup{OwnedDataRetained: true, Errors: []string{}}}
	if e = os.Mkdir(v.root, 0700); e != nil {
		return e
	}
	v.synthetic, e = newSyntheticRoot(v.root, prepare.Session)
	if e != nil {
		return e
	}
	seq := uint64(0)
	emit := func(kind string, guest *GuestResult, cleanup *Cleanup, message string) error {
		event := Event{Version: 1, Source: buildSource, Session: prepare.Session, Seq: seq, Kind: kind, VMID: v.id, RuntimeID: v.runtimeID, Guest: guest, Cleanup: cleanup, Error: message}
		seq++
		return writeFrame(os.Stdout, &written, event)
	}
	if e = emit("prepared", nil, nil, ""); e != nil {
		return errors.Join(e, v.synthetic.close())
	}
	var start Request
	if e = readFrame(os.Stdin, &read, &start); e != nil {
		return errors.Join(e, v.synthetic.close())
	}
	if start.Op == "cancel" {
		e = validateRequest(start, buildSource, prepare.Session, 1, "cancel")
		if e != nil || start.Fixture != prepare.Fixture {
			return errors.Join(e, errors.New("cancel fixture binding"), v.synthetic.close())
		}
		v.receipt.Quarantine = "not-started"
		v.receipt.InputSHA256 = v.synthetic.inputSHA
		v.record("synthetic_handles", v.synthetic.close())
		if e = emit("cleanup", nil, &v.receipt, ""); e != nil {
			return e
		}
		if len(v.receipt.Errors) != 0 {
			return errors.New("pre-start close failure")
		}
		return nil
	}
	if e = validateRequest(start, buildSource, prepare.Session, 1, "start"); e != nil || start.Fixture != prepare.Fixture {
		return errors.Join(e, errors.New("start operation"), v.synthetic.close())
	}
	if e = emit("creating", nil, nil, ""); e != nil {
		return errors.Join(e, v.synthetic.close())
	}
	ctx, stop := context.WithTimeout(context.Background(), 6*time.Minute)
	defer stop()
	ran := make(chan error, 1)
	go func() { ran <- v.start(ctx, start, emit) }()
	control := make(chan controlResult, 1)
	readDone := make(chan struct{})
	go func() {
		defer close(readDone)
		var r Request
		e := readFrame(os.Stdin, &read, &r)
		control <- controlResult{r, e}
	}()
	cancelled, ready := false, false
	select {
	case e = <-ran:
		ready = true
	case r := <-control:
		cancelled = r.request.Op != "finish"
		op := "finish"
		if cancelled {
			op = "cancel"
			if !v.guestReady.Load() {
				stop()
			}
		}
		if r.err != nil {
			v.record("control", r.err)
			cancelled = true
			stop()
		} else if x := validateRequest(r.request, buildSource, prepare.Session, 2, op); x != nil || r.request.Fixture != prepare.Fixture {
			v.record("control", errors.Join(x, errors.New("control binding")))
			cancelled = true
			stop()
		}
		e = <-ran

	}
	if e != nil && e != context.Canceled {
		v.record("run", e)
		cancelled = true
		stop()
	}
	if ready && e == nil {
		select {
		case r := <-control:
			cancelled = r.request.Op == "cancel"
			op := "finish"
			if cancelled {
				op = "cancel"
			}
			if r.err != nil {
				v.record("control", r.err)
				cancelled = true
			} else if x := validateRequest(r.request, buildSource, prepare.Session, 2, op); x != nil || r.request.Fixture != prepare.Fixture {
				v.record("control", errors.Join(x, errors.New("control fixture binding")))
				cancelled = true
			}
		case <-ctx.Done():
			v.record("control_deadline", ctx.Err())
			cancelled = true
		}
	}
	// Even cancelled ready sessions close the supervisor first; its detached child
	// remains inside the UVM until the independent whole-VM termination below.
	if e == nil && v.guestReady.Load() && len(v.receipt.Errors) == 0 {
		finish, end := context.WithTimeout(context.Background(), 10*time.Second)
		v.record("supervisor_finish", v.guest.finish(finish))
		end()
	}
	stop()
	if e = os.Stdin.Close(); e != nil {
		v.record("host_input_close", e)
	}
	select {
	case <-readDone:
	case <-time.After(10 * time.Second):
		v.record("host_input_join", errors.New("request reader not joined"))
	}
	v.close(cancelled)
	if e = emit("cleanup", nil, &v.receipt, ""); e != nil {
		return e
	}
	if !completeCleanup(v.receipt, cancelled) {
		return errors.New("owned VM completion uncertain")
	}
	return nil
}
func main() {
	if len(os.Args) != 3 {
		os.Exit(90)
	}
	var e error
	switch os.Args[1] {
	case "--import-root":
		e = importLayers(os.Args[2])
	case "--session-root":
		e = runSession(os.Args[2])
	default:
		e = errors.New("fixed broker mode required")
	}
	if e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(91)
	}
}
