//go:build windows && !fixture

package main

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"sync"
	"time"

	"github.com/Microsoft/hcsshim/internal/cow"
	hcsschema "github.com/Microsoft/hcsshim/internal/hcs/schema2"
)

type policyLine struct {
	text []byte
	err  error
}
type policySession struct {
	p           cow.Process
	input       io.Writer
	out, stderr chan policyLine
	ctx         context.Context
	cancel      context.CancelFunc
	tasks       sync.WaitGroup
}

func (s *policySession) readLines(r io.Reader, ch chan policyLine) {
	defer s.tasks.Done()
	defer close(ch)
	scan := bufio.NewScanner(r)
	scan.Buffer(make([]byte, 4096), policyFrameLimit+1)
	total := 0
	for scan.Scan() {
		b := append([]byte(nil), scan.Bytes()...)
		total += len(b)
		if total > 4*policyFrameLimit {
			select {
			case ch <- policyLine{err: errors.New("stream aggregate bound")}:
			case <-s.ctx.Done():
			}
			return
		}
		select {
		case ch <- policyLine{text: b}:
		case <-s.ctx.Done():
			return
		}
	}
	if e := scan.Err(); e != nil {
		select {
		case ch <- policyLine{err: e}:
		case <-s.ctx.Done():
		}
	}
}
func (s *policySession) line(ctx context.Context, ch chan policyLine) ([]byte, error) {
	select {
	case l, ok := <-ch:
		if !ok {
			return nil, errors.New("unexpected policy stream EOF")
		}
		return l.text, l.err
	case <-ctx.Done():
		return nil, ctx.Err()
	}
}
func startPolicySession(ctx context.Context, host cow.ProcessHost) (*policySession, error) {
	p, e := host.CreateProcess(ctx, &hcsschema.ProcessParameters{CommandLine: `"` + workspace + `\fixture.exe" policy`, User: "ContainerUser", WorkingDirectory: workspace,
		Environment: map[string]string{"POWERSHELL_TELEMETRY_OPTOUT": "1", "POWERSHELL_UPDATECHECK": "Off"}, CreateStdInPipe: true, CreateStdOutPipe: true, CreateStdErrPipe: true})
	if e != nil {
		return nil, e
	}
	child, cancel := context.WithCancel(ctx)
	s := &policySession{p: p, ctx: child, cancel: cancel, out: make(chan policyLine), stderr: make(chan policyLine)}
	in, out, stderr := p.Stdio()
	s.input = in
	if in == nil || out == nil || stderr == nil {
		return s, errors.New("missing persistent stdio")
	}
	s.tasks.Add(2)
	go s.readLines(out, s.out)
	go s.readLines(stderr, s.stderr)
	b, e := s.line(ctx, s.out)
	if e != nil {
		return s, e
	}
	var reply policyReply
	if e = decodePolicyFrame(b, &reply); e != nil || reply.Phase != "ready" || reply.Nonce != "" || len(reply.Cases)+len(reply.Dials) != 0 || reply.Error != "" {
		return s, errors.New("supervisor ready receipt")
	}
	b, e = s.line(ctx, s.stderr)
	if e != nil || string(b) != "CTM_POLICY_STDERR_READY" {
		return s, errors.New("supervisor stderr ready receipt")
	}
	return s, nil
}
func (s *policySession) exchange(ctx context.Context, phase, nonce string, ids []string) (reply policyReply, err error) {
	b, err := json.Marshal(policyRequest{Phase: phase, Nonce: nonce, Services: ids})
	if err != nil {
		return reply, err
	}
	write := make(chan error, 1)
	s.tasks.Add(1)
	go func() {
		defer s.tasks.Done()
		n, e := s.input.Write(append(b, '\n'))
		if e == nil && n != len(b)+1 {
			e = io.ErrShortWrite
		}
		write <- e
	}()
	select {
	case err = <-write:
	case <-ctx.Done():
		err = ctx.Err()
	}
	if err != nil {
		return reply, err
	}
	b, err = s.line(ctx, s.out)
	if err != nil {
		return reply, err
	}
	if err = decodePolicyFrame(b, &reply); err != nil {
		return reply, err
	}
	if reply.Phase != phase || reply.Nonce != nonce || reply.Error != "" {
		return reply, fmt.Errorf("reply phase/nonce/error: %s", reply.Error)
	}
	b, err = s.line(ctx, s.stderr)
	if err != nil || string(b) != "CTM_POLICY_STDERR_"+phase+" "+nonce {
		return reply, errors.New("stderr continuity receipt")
	}
	return reply, nil
}
func (s *policySession) finish(ctx context.Context) error {
	if e := s.p.CloseStdin(ctx); e != nil {
		return e
	}
	for _, ch := range []chan policyLine{s.out, s.stderr} {
		select {
		case _, ok := <-ch:
			if ok {
				return errors.New("extra supervisor output")
			}
		case <-ctx.Done():
			return ctx.Err()
		}
	}
	waited := make(chan error, 1)
	s.tasks.Add(1)
	go func() { defer s.tasks.Done(); waited <- s.p.Wait() }()
	select {
	case e := <-waited:
		if e != nil {
			return e
		}
	case <-ctx.Done():
		return ctx.Err()
	}
	code, e := s.p.ExitCode()
	if e != nil || code != 23 {
		return fmt.Errorf("supervisor exit %d: %v", code, e)
	}
	return nil
}
func (s *policySession) close() error {
	if s == nil {
		return nil
	}
	s.cancel()
	ctx, stop := context.WithTimeout(context.Background(), 5*time.Second)
	defer stop()
	e := errors.Join(s.p.CloseStdout(ctx), s.p.CloseStderr(ctx), s.p.Close())
	joined := make(chan struct{})
	go func() { s.tasks.Wait(); close(joined) }()
	select {
	case <-joined:
		return e
	case <-ctx.Done():
		return errors.Join(e, errors.New("persistent IO tasks not joined"))
	}
}
