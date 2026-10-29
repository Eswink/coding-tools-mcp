//go:build windows && !guest

package main

import (
	"context"
	"errors"
	"io"
	"sync"
	"time"

	"github.com/Microsoft/hcsshim/internal/cow"
	hcsschema "github.com/Microsoft/hcsshim/internal/hcs/schema2"
)

type guestFrame struct {
	value GuestResult
	err   error
}
type guestProcess struct {
	streamErr, frameErr, waitErr, writeErr error
	stdinOnce                              sync.Once
	stdinErr                               error
	p                                      cow.Process
	in                                     io.Writer
	out, stderr                            io.Reader
	tasks                                  sync.WaitGroup
	frames                                 chan guestFrame
	waited                                 chan error
	errors                                 boundedOutput
	readTotal, writeTotal                  int
	cancel                                 context.CancelFunc
}

func (g *guestProcess) closeStdin() error {
	g.stdinOnce.Do(func() {
		ctx, stop := context.WithTimeout(context.Background(), 10*time.Second)
		defer stop()
		g.stdinErr = g.p.CloseStdin(ctx)
	})
	return g.stdinErr
}

func openGuestProcess(ctx context.Context, host cow.ProcessHost, command, cwd string) (g *guestProcess, err error) {
	p, e := host.CreateProcess(ctx, &hcsschema.ProcessParameters{CommandLine: command, User: "ContainerUser", WorkingDirectory: cwd,
		Environment: map[string]string{"POWERSHELL_TELEMETRY_OPTOUT": "1", "POWERSHELL_UPDATECHECK": "Off"}, CreateStdInPipe: true, CreateStdOutPipe: true, CreateStdErrPipe: true})
	if e != nil {
		return nil, e
	}
	g = &guestProcess{p: p, waited: make(chan error, 2)}
	g.in, g.out, g.stderr = p.Stdio()
	if g.in == nil || g.out == nil || g.stderr == nil {
		return g, errors.New("missing HCS stdio")
	}
	return g, nil
}
func (g *guestProcess) bootstrap(ctx context.Context, input io.Reader) error {
	var out boundedOutput
	done := make(chan error, 4)
	g.tasks.Add(4)
	go func() {
		defer g.tasks.Done()
		_, e := io.Copy(g.in, input)
		g.writeErr = errors.Join(e, g.closeStdin())
		done <- g.writeErr
	}()
	go func() {
		defer g.tasks.Done()
		_, g.frameErr = io.Copy(&out, g.out)
		if out.overflow {
			g.frameErr = errors.Join(g.frameErr, errors.New("bootstrap stdout overflow"))
		}
		done <- g.frameErr
	}()
	go func() { defer g.tasks.Done(); _, g.streamErr = io.Copy(&g.errors, g.stderr); done <- g.streamErr }()
	go func() { defer g.tasks.Done(); g.waitErr = g.p.Wait(); done <- g.waitErr }()
	var err error
	for i := 0; i < 4; i++ {
		select {
		case e := <-done:
			err = errors.Join(err, e)
		case <-ctx.Done():
			return errors.Join(err, ctx.Err())
		}
	}
	code, e := g.p.ExitCode()
	err = errors.Join(err, e)
	if code != 23 || out.String() != "CTM_VM_BOOTSTRAP\r\n" || g.errors.Len() != 0 || out.overflow || g.errors.overflow {
		return errors.Join(err, errors.New("bootstrap receipt"))
	}
	return err
}
func (g *guestProcess) startFrames(ctx context.Context) error {
	child, cancel := context.WithCancel(ctx)
	g.cancel = cancel
	g.frames = make(chan guestFrame, 1)
	g.tasks.Add(3)
	go func() {
		defer g.tasks.Done()
		defer close(g.frames)
		seen := 0
		for {
			var v GuestResult
			e := readFrame(g.out, &g.readTotal, &v)
			if e == nil {
				seen++
				if seen > 2 {
					e = errors.New("extra guest protocol frame")
				}
			}
			if e != nil && e != io.EOF {
				g.frameErr = e
			}
			select {
			case g.frames <- guestFrame{v, e}:
			case <-child.Done():
				return
			}
			if e != nil {
				return
			}
		}
	}()
	go func() {
		defer g.tasks.Done()
		_, e := io.Copy(&g.errors, g.stderr)
		g.streamErr = e
	}()
	go func() { defer g.tasks.Done(); g.waitErr = g.p.Wait(); g.waited <- g.waitErr }()
	ready, e := g.next(ctx)
	if e != nil {
		return e
	}
	if len(ready.Cases) != 1 || ready.Cases[0].Name != "ready" || !ready.Cases[0].Passed || ready.Cases[0].ExitCode != 0 || ready.Cases[0].Stdout != "" || ready.Cases[0].Stderr != "" || ready.ChildAlive || ready.InputSHA256 != "" || ready.OutputSHA256 != "" || ready.DataBase64 != "" {
		return errors.New("guest ready receipt")
	}
	return nil
}
func (g *guestProcess) next(ctx context.Context) (GuestResult, error) {
	select {
	case f, ok := <-g.frames:
		if !ok {
			return GuestResult{}, io.ErrUnexpectedEOF
		}
		return f.value, f.err
	case <-ctx.Done():
		return GuestResult{}, ctx.Err()
	}
}
func (g *guestProcess) exchange(ctx context.Context, r GuestRequest) (GuestResult, error) {
	done := make(chan error, 1)
	g.tasks.Add(1)
	go func() { defer g.tasks.Done(); g.writeErr = writeFrame(g.in, &g.writeTotal, r); done <- g.writeErr }()
	select {
	case e := <-done:
		if e != nil {
			return GuestResult{}, e
		}
	case <-ctx.Done():
		return GuestResult{}, ctx.Err()
	}
	return g.next(ctx)
}
func (g *guestProcess) finish(ctx context.Context) error {
	if e := g.closeStdin(); e != nil {
		return e
	}
	if _, e := g.next(ctx); e != io.EOF {
		return errors.Join(errors.New("expected guest EOF"), e)
	}
	select {
	case e := <-g.waited:
		if e != nil {
			return e
		}
	case <-ctx.Done():
		return ctx.Err()
	}
	code, e := g.p.ExitCode()
	if code != 23 {
		return errors.Join(errors.New("guest supervisor exit"), e)
	}
	return e
}
func (g *guestProcess) close() (joined bool, err error) {
	if g == nil {
		return true, nil
	}
	if g.cancel != nil {
		g.cancel()
	}
	ctx, stop := context.WithTimeout(context.Background(), 10*time.Second)
	defer stop()
	// Whole-VM exit already proved. Full Close releases pending accept channels;
	// starting/awaiting another half-close here can block before they are released.
	err = errors.Join(g.p.Close(), g.p.CloseStdout(ctx), g.p.CloseStderr(ctx))
	done := make(chan struct{})
	go func() { g.tasks.Wait(); close(done) }()
	select {
	case <-done:
		joined = true
	case <-ctx.Done():
		err = errors.Join(err, errors.New("guest IO not joined"))
	}
	if joined {
		err = errors.Join(err, g.streamErr, g.frameErr, g.waitErr, g.writeErr)
	}
	if joined && (g.errors.overflow || g.errors.Len() != 0) {
		err = errors.Join(err, errors.New("guest stderr or overflow"))
	}
	return
}
