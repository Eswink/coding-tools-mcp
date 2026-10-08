//go:build windows

package main

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"errors"
	"github.com/Microsoft/go-winio"
	"github.com/Microsoft/go-winio/pkg/guid"
	"io"
	"strings"
	"syscall"
	"time"
	"unicode/utf16"
)

const workspace = `C:\Users\ContainerUser\ctm-workspace`
const powershell = `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`
const outputLimit = 65536

type caseResult struct {
	Name     string `json:"name"`
	Stdout   string `json:"stdout"`
	Stderr   string `json:"stderr"`
	ExitCode int    `json:"exit_code"`
	Passed   bool   `json:"passed"`
}

func encodedCommand(script string) string {
	u := utf16.Encode([]rune(script))
	b := make([]byte, len(u)*2)
	for i, v := range u {
		binary.LittleEndian.PutUint16(b[i*2:], v)
	}
	return `"` + powershell + `" -NoLogo -NoProfile -NonInteractive -EncodedCommand ` + base64.StdEncoding.EncodeToString(b)
}

type boundedOutput struct {
	buffer   bytes.Buffer // Named field prevents promoted ReadFrom from bypassing Write.
	overflow bool
}

func (b *boundedOutput) Len() int       { return b.buffer.Len() }
func (b *boundedOutput) String() string { return b.buffer.String() }

func (b *boundedOutput) Write(p []byte) (int, error) {
	n := len(p)
	room := outputLimit - b.Len()
	if n > room {
		b.overflow = true
		p = p[:room]
	}
	b.buffer.Write(p)
	return n, nil
}
func runtimeCommands() []struct{ name, command, marker string } {
	ps := `$ErrorActionPreference='Stop';[IO.File]::WriteAllText('roundtrip-ps.txt','CTM_PS');if([IO.File]::ReadAllText('roundtrip-ps.txt') -cne 'CTM_PS'){exit 91};[Console]::WriteLine('CTM_PS_ENTRY '+$PSVersionTable.PSVersion);exit 23`
	pw := `$ErrorActionPreference='Stop';[IO.File]::WriteAllText('roundtrip-pwsh.txt','CTM_PWSH');if([IO.File]::ReadAllText('roundtrip-pwsh.txt') -cne 'CTM_PWSH'){exit 91};[Console]::WriteLine('CTM_PWSH_ENTRY '+$PSVersionTable.PSVersion);exit 23`
	return []struct{ name, command, marker string }{
		{"cmd", `C:\Windows\System32\cmd.exe /d /s /c ">roundtrip-cmd.txt echo CTM_CMD&& C:\Windows\System32\findstr.exe /x CTM_CMD roundtrip-cmd.txt&& echo CTM_CMD_ENTRY&& exit /b 23"`, "CTM_CMD_ENTRY"},
		{"windows-powershell", encodedCommand(ps), "CTM_PS_ENTRY"},
		{"node", `"` + workspace + `\node.exe" -e "const f=require('fs');f.writeFileSync('roundtrip-node.txt','CTM_NODE');if(f.readFileSync('roundtrip-node.txt','utf8')!=='CTM_NODE')process.exit(91);console.log('CTM_NODE_ENTRY '+process.version);process.exit(23)"`, "CTM_NODE_ENTRY"},
		{"pwsh", strings.Replace(encodedCommand(pw), powershell, workspace+`\pwsh\pwsh.exe`, 1), "CTM_PWSH_ENTRY"},
	}
}

const policyNonceBytes = 32
const policyFrameLimit = 32768

type policyRequest struct {
	Phase    string   `json:"phase"`
	Nonce    string   `json:"nonce"`
	Services []string `json:"services"`
}
type dialObservation struct {
	Target     string `json:"target_vmid"`
	Service    string `json:"service"`
	Connected  bool   `json:"connected"`
	Echo       bool   `json:"echo"`
	ErrorCode  uint32 `json:"error_code"`
	Error      string `json:"error"`
	CloseError string `json:"close_error"`
}
type listenerReceipt struct {
	Ready    bool   `json:"ready"`
	Closed   bool   `json:"closed"`
	Accepted int    `json:"accepted"`
	Error    string `json:"error"`
}
type policyReply struct {
	Listener *listenerReceipt  `json:"listener,omitempty"`
	Phase    string            `json:"phase"`
	Nonce    string            `json:"nonce"`
	Dials    []dialObservation `json:"dials"`
	Cases    []caseResult      `json:"cases"`
	Error    string            `json:"error"`
}

func decodePolicyFrame(b []byte, v any) error {
	if len(b) == 0 || len(b) > policyFrameLimit {
		return errors.New("policy frame bound")
	}
	d := json.NewDecoder(bytes.NewReader(b))
	d.DisallowUnknownFields()
	if e := d.Decode(v); e != nil {
		return e
	}
	var extra any
	if e := d.Decode(&extra); e != io.EOF {
		return errors.New("trailing policy frame")
	}
	return nil
}
func validPolicyRequest(r policyRequest, phase, nonce string, ids []string) bool {
	if r.Phase != phase || len(r.Nonce) != policyNonceBytes || r.Nonce != nonce || len(r.Services) != 5 || len(ids) != 5 {
		return false
	}
	for i := range ids {
		if ids[i] == "" || r.Services[i] != ids[i] {
			return false
		}
	}
	return true
}
func policyDialDenied(o dialObservation) bool {
	// Timeouts, missing routes and unknown errors are never accepted as policy proof.
	return !o.Connected && !o.Echo && o.CloseError == "" && (o.ErrorCode == 10013 || o.ErrorCode == 10061)
}

func registrationMatches(values, subkeys, kind uint32, value, marker string) bool {
	return values == 1 && subkeys == 0 && kind == 1 && value == marker && len(marker) == 47 && strings.HasPrefix(marker, "ctm-static-hvs:")
}
func policyDial(id, nonce string, vmID guid.GUID) (o dialObservation) {
	o.Service = id
	o.Target = vmID.String()
	g, e := guid.FromString(id)
	if e != nil {
		o.Error = e.Error()
		return
	}
	ctx, stop := context.WithTimeout(context.Background(), 2*time.Second)
	defer stop()
	c, e := winio.Dial(ctx, &winio.HvsockAddr{VMID: vmID, ServiceID: g})
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
