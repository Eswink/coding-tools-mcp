//go:build windows && guest

package main

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/binary"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strings"
	"syscall"
	"time"
	"unicode/utf16"
)

const workspace = `C:\Users\ContainerUser\ctm-workspace`
const powershell = `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`

func guestHash(b []byte) string { v := sha256.Sum256(b); return hex.EncodeToString(v[:]) }
func encodedCommand(script string) string {
	u := utf16.Encode([]rune(script))
	b := make([]byte, len(u)*2)
	for i, v := range u {
		binary.LittleEndian.PutUint16(b[i*2:], v)
	}
	return `"` + powershell + `" -NoLogo -NoProfile -NonInteractive -EncodedCommand ` + base64.StdEncoding.EncodeToString(b)
}
func runtimeCommands() []struct{ name, executable, command, marker string } {
	ps := `$ErrorActionPreference='Stop';[IO.File]::WriteAllText('roundtrip-ps.txt','CTM_PS');if([IO.File]::ReadAllText('roundtrip-ps.txt') -cne 'CTM_PS'){exit 91};[Console]::WriteLine('CTM_PS_ENTRY '+$PSVersionTable.PSVersion);exit 23`
	pw := strings.ReplaceAll(strings.ReplaceAll(ps, "roundtrip-ps", "roundtrip-pwsh"), "CTM_PS", "CTM_PWSH")
	return []struct{ name, executable, command, marker string }{
		{"cmd", `C:\Windows\System32\cmd.exe`, `C:\Windows\System32\cmd.exe /d /s /c ">roundtrip-cmd.txt echo CTM_CMD&& C:\Windows\System32\findstr.exe /x CTM_CMD roundtrip-cmd.txt&& echo CTM_CMD_ENTRY&& exit /b 23"`, "CTM_CMD_ENTRY"},
		{"windows-powershell", powershell, encodedCommand(ps), "CTM_PS_ENTRY"},
		{"node", workspace + `\node.exe`, `"` + workspace + `\node.exe" -e "const f=require('fs');f.writeFileSync('roundtrip-node.txt','CTM_NODE');if(f.readFileSync('roundtrip-node.txt','utf8')!=='CTM_NODE')process.exit(91);console.log('CTM_NODE_ENTRY '+process.version);process.exit(23)"`, "CTM_NODE_ENTRY"},
		{"pwsh", workspace + `\pwsh\pwsh.exe`, strings.Replace(encodedCommand(pw), powershell, workspace+`\pwsh\pwsh.exe`, 1), "CTM_PWSH_ENTRY"},
	}
}
func runCommand(name, exe, command, marker string) Case {
	r := Case{Name: name, ExitCode: -1}
	ctx, stop := context.WithTimeout(context.Background(), 25*time.Second)
	defer stop()
	cmd := exec.CommandContext(ctx, exe)
	cmd.SysProcAttr = &syscall.SysProcAttr{CmdLine: command}
	cmd.Dir = workspace
	var out, stderr boundedOutput
	cmd.Stdout = &out
	cmd.Stderr = &stderr
	e := cmd.Run()
	if cmd.ProcessState != nil {
		r.ExitCode = cmd.ProcessState.ExitCode()
	}
	r.Stdout = out.String()
	r.Stderr = stderr.String()
	var exited *exec.ExitError
	r.Passed = (e == nil || errors.As(e, &exited)) && ctx.Err() == nil && !out.overflow && !stderr.overflow && r.ExitCode == 23 && strings.Contains(r.Stdout, marker) && r.Stderr == ""
	return r
}
func runGuestFixture() error {
	read, written := 0, 0
	ready := GuestResult{Cases: []Case{{Name: "ready", Passed: true}}}
	if e := writeFrame(os.Stdout, &written, ready); e != nil {
		return e
	}
	var request GuestRequest
	if e := readFrame(os.Stdin, &read, &request); e != nil {
		return e
	}
	r := request.Request
	if e := validateRequest(r, buildSource, r.Session, 1, "start"); e != nil {
		return e
	}
	data, e := base64.StdEncoding.Strict().DecodeString(request.DataBase64)
	if e != nil || len(data) > 1024 || string(data) != "ctm-synthetic:"+r.Session || guestHash(data) != request.InputSHA256 {
		return errors.New("guest input binding")
	}
	if e = os.WriteFile("input.bin", data, 0600); e != nil {
		return e
	}
	observed, e := os.ReadFile("input.bin")
	if e != nil || !strings.EqualFold(string(observed), string(data)) || guestHash(observed) != request.InputSHA256 {
		return errors.New("guest input readback")
	}
	output := []byte(strings.ToUpper(string(observed)))
	result := GuestResult{Cases: []Case{}, InputSHA256: request.InputSHA256, OutputSHA256: guestHash(output), DataBase64: base64.StdEncoding.EncodeToString(output)}
	var child *exec.Cmd
	if r.Fixture == "runtimes" {
		for _, c := range runtimeCommands() {
			result.Cases = append(result.Cases, runCommand(c.name, c.executable, c.command, c.marker))
		}
	} else {
		child = exec.Command(workspace+`\guest.exe`, "--child")
		child.Dir = workspace
		if e = child.Start(); e != nil {
			return e
		}
		exited := make(chan error, 1)
		go func() { exited <- child.Wait() }()
		select {
		case <-exited:
			return errors.New("child exited early")
		case <-time.After(200 * time.Millisecond):
			result.ChildAlive = true
		}
	}
	if e = writeFrame(os.Stdout, &written, result); e != nil {
		return e
	}
	var extra [1]byte
	n, e := os.Stdin.Read(extra[:])
	if n != 0 || e != io.EOF {
		return errors.New("extra guest command")
	}
	return nil
}
func main() {
	if len(os.Args) == 2 && os.Args[1] == "--child" {
		for {
			time.Sleep(time.Second)
		}
	}
	mode, e := selectGuestMode(os.Args[1:])
	if e != nil {
		os.Exit(90)
	}
	if mode == guestFixtureMode {
		e = runGuestFixture()
	} else {
		e = runGuestWorkspace()
	}
	if e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(91)
	}
	os.Exit(23)
}
