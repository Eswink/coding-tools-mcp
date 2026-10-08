//go:build windows && fixture

package main

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"os/exec"
	"strings"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/Microsoft/go-winio"
	"github.com/Microsoft/go-winio/pkg/guid"
)

func runPolicyCommand(name, executable, command, marker string) caseResult {
	c := caseResult{Name: name, ExitCode: -1}
	ctx, stop := context.WithTimeout(context.Background(), 25*time.Second)
	defer stop()
	cmd := exec.CommandContext(ctx, executable)
	cmd.SysProcAttr = &syscall.SysProcAttr{CmdLine: command}
	cmd.Dir = workspace
	var out, stderr boundedOutput
	cmd.Stdout = &out
	cmd.Stderr = &stderr
	e := cmd.Run()
	if cmd.ProcessState != nil {
		c.ExitCode = cmd.ProcessState.ExitCode()
	}
	c.Stdout = out.String()
	c.Stderr = stderr.String()
	var exit *exec.ExitError
	validExit := e == nil || errors.As(e, &exit)
	c.Passed = validExit && ctx.Err() == nil && !out.overflow && !stderr.overflow && c.ExitCode == 23 && strings.Contains(c.Stdout, marker) && c.Stderr == ""
	return c
}
func policyRuntimeCases() []caseResult {
	paths := []string{`C:\Windows\System32\cmd.exe`, powershell, workspace + `\node.exe`, workspace + `\pwsh\pwsh.exe`}
	var results []caseResult
	for i, c := range runtimeCommands() {
		results = append(results, runPolicyCommand(c.name, paths[i], c.command, c.marker))
	}
	self := workspace + `\fixture.exe`
	for _, mode := range []string{"parent", "check"} {
		marker := "CTM_PARENT_ENTRY"
		if mode == "check" {
			marker = "CTM_CHILD_LIVE"
		}
		results = append(results, runPolicyCommand(mode, self, `"`+self+`" `+mode, marker))
	}
	return results
}
func writePolicyReply(r policyReply) error {
	b, e := json.Marshal(r)
	if e != nil {
		return e
	}
	if len(b) > policyFrameLimit {
		return errors.New("reply bound")
	}
	_, e = fmt.Fprintln(os.Stdout, string(b))
	return e
}

type guestCanary struct {
	l       net.Listener
	closing atomic.Bool
	done    chan listenerReceipt
}

func newGuestCanary(id, nonce string) (*guestCanary, error) {
	g, e := guid.FromString(id)
	if e != nil {
		return nil, e
	}
	// A hosted-container Parent listener addresses the UVM; wildcard is required for host connections.
	l, e := winio.ListenHvsock(&winio.HvsockAddr{VMID: winio.HvsockGUIDWildcard(), ServiceID: g})
	if e != nil {
		return nil, e
	}
	c := &guestCanary{l: l, done: make(chan listenerReceipt, 1)}
	go func() {
		r := listenerReceipt{Ready: true}
		conn, e := l.Accept()
		if e != nil {
			if !c.closing.Load() {
				r.Error = e.Error()
			}
			c.done <- r
			return
		}
		r.Accepted = 1
		e = conn.SetDeadline(time.Now().Add(2 * time.Second))
		b := make([]byte, len(nonce))
		if e == nil {
			_, e = io.ReadFull(conn, b)
		}
		if e == nil && string(b) != nonce {
			e = errors.New("guest listener nonce mismatch")
		}
		if e == nil {
			_, e = conn.Write(b)
		}
		e = errors.Join(e, conn.Close())
		if e != nil {
			r.Error = e.Error()
		}
		c.done <- r
	}()
	return c, nil
}
func (c *guestCanary) close() listenerReceipt {
	c.closing.Store(true)
	e := c.l.Close()
	select {
	case r := <-c.done:
		if e != nil {
			r.Error += e.Error()
		}
		r.Closed = r.Error == ""
		return r
	case <-time.After(5 * time.Second):
		return listenerReceipt{Ready: true, Error: "guest listener task not joined"}
	}
}
func runPolicyFixture() error {
	scan := bufio.NewScanner(os.Stdin)
	scan.Buffer(make([]byte, 4096), policyFrameLimit+1)
	if e := writePolicyReply(policyReply{Phase: "ready"}); e != nil {
		return e
	}
	if _, e := fmt.Fprintln(os.Stderr, "CTM_POLICY_STDERR_READY"); e != nil {
		return e
	}
	nonce := ""
	var ids []string
	var listener *guestCanary
	phases := []string{"", "guest-listen", "guest-close", "runtimes", "finish"}
	for i := 0; i < len(phases); i++ {
		if !scan.Scan() {
			return errors.New("missing policy request")
		}
		var request policyRequest
		if e := decodePolicyFrame(scan.Bytes(), &request); e != nil {
			return e
		}
		if i == 0 {
			if request.Phase != "control" && request.Phase != "restricted" {
				return errors.New("invalid static profile")
			}
			phases[0] = request.Phase
			if request.Phase == "control" {
				phases = []string{"control", "guest-listen", "guest-close", "finish"}
			}
			nonce = request.Nonce
			ids = append([]string(nil), request.Services...)
			seen := map[string]bool{}
			for _, id := range ids {
				g, e := guid.FromString(id)
				if e != nil || seen[id] || g.Data3>>12 != 4 {
					return errors.New("invalid owned GUID inventory")
				}
				seen[id] = true
			}
		}
		phase := phases[i]
		if !validPolicyRequest(request, phase, nonce, ids) {
			return errors.New("policy request identity/sequence")
		}
		reply := policyReply{Phase: phase, Nonce: nonce}
		switch phase {
		case "control", "restricted":
			for _, id := range ids[:4] {
				reply.Dials = append(reply.Dials, policyDial(id, nonce, winio.HvsockGUIDParent()))
			}
		case "guest-listen":
			var e error
			listener, e = newGuestCanary(ids[4], nonce)
			if e != nil {
				reply.Error = e.Error()
			} else {
				reply.Listener = &listenerReceipt{Ready: true}
			}
		case "guest-close":
			r := listener.close()
			reply.Listener = &r
			reply.Error = r.Error
		case "runtimes":
			reply.Cases = policyRuntimeCases()
		}
		if _, e := fmt.Fprintln(os.Stderr, "CTM_POLICY_STDERR_"+phase+" "+nonce); e != nil {
			return e
		}
		if e := writePolicyReply(reply); e != nil {
			return e
		}
		if reply.Error != "" {
			return errors.New(reply.Error)
		}
	}
	if scan.Scan() || scan.Err() != nil {
		return errors.New("extra policy request")
	}
	return nil
}
