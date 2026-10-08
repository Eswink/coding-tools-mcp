//go:build windows && fixture

package main

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strings"
	"syscall"
	"time"

	"github.com/Microsoft/go-winio"
	"github.com/Microsoft/go-winio/pkg/guid"
)

func policyDial(id, nonce string) (o dialObservation) {
	o.Service = id
	g, e := guid.FromString(id)
	if e != nil {
		o.Error = e.Error()
		return
	}
	ctx, stop := context.WithTimeout(context.Background(), 2*time.Second)
	defer stop()
	c, e := winio.Dial(ctx, &winio.HvsockAddr{VMID: winio.HvsockGUIDParent(), ServiceID: g})
	if e != nil {
		o.Error = e.Error()
		var n syscall.Errno
		if errors.As(e, &n) {
			o.ErrorCode = uint32(n)
		}
		return
	}
	o.Connected = true
	defer func() {
		if e := c.Close(); e != nil {
			o.CloseError = e.Error()
		}
	}()
	if e = c.SetDeadline(time.Now().Add(2 * time.Second)); e == nil {
		_, e = io.WriteString(c, nonce)
	}
	b := make([]byte, len(nonce))
	if e == nil {
		_, e = io.ReadFull(c, b)
	}
	if e != nil {
		o.Error = e.Error()
		return
	}
	o.Echo = string(b) == nonce
	return
}
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
	for _, phase := range []string{"positive", "negative", "runtimes", "finish"} {
		if !scan.Scan() {
			return errors.New("missing policy request")
		}
		var request policyRequest
		if e := decodePolicyFrame(scan.Bytes(), &request); e != nil {
			return e
		}
		if phase == "positive" {
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
		if !validPolicyRequest(request, phase, nonce, ids) {
			return errors.New("policy request identity/sequence")
		}
		reply := policyReply{Phase: phase, Nonce: nonce}
		switch phase {
		case "positive", "negative":
			for _, id := range ids {
				reply.Dials = append(reply.Dials, policyDial(id, nonce))
			}
		case "runtimes":
			reply.Cases = policyRuntimeCases()
		}
		if _, e := fmt.Fprintln(os.Stderr, "CTM_POLICY_STDERR_"+phase+" "+nonce); e != nil {
			return e
		}
		if e := writePolicyReply(reply); e != nil {
			return e
		}
	}
	// Host half-closes stdin; no extra command or open stream is silently accepted.
	if scan.Scan() || scan.Err() != nil {
		return errors.New("extra policy request")
	}
	return nil
}
