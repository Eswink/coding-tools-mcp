//go:build windows && fixture

package main

import (
	"fmt"
	"golang.org/x/sys/windows"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

// Only synthetic guest files and this same guest executable are used.
func main() {
	if len(os.Args) != 2 {
		os.Exit(90)
	}
	switch os.Args[1] {
	case "surface":
		if err := runSurfaceFixture(); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(90)
		}
		os.Exit(23)
	case "child":
		if os.WriteFile("child.pid", []byte(strconv.Itoa(os.Getpid())), 0600) != nil {
			os.Exit(91)
		}
		for {
			time.Sleep(time.Second)
		}
	case "parent":
		self, err := os.Executable()
		if err != nil {
			os.Exit(92)
		}
		child := exec.Command(self, "child") // nil stdio: no inherited HCS pipe keeps parent I/O open.
		if child.Start() != nil {
			os.Exit(93)
		}
		for i := 0; i < 100; i++ {
			if b, e := os.ReadFile("child.pid"); e == nil && string(b) == strconv.Itoa(child.Process.Pid) {
				fmt.Println("CTM_PARENT_ENTRY", child.Process.Pid)
				os.Exit(23)
			}
			time.Sleep(50 * time.Millisecond)
		}
		os.Exit(94)
	case "check":
		b, err := os.ReadFile("child.pid")
		if err != nil {
			os.Exit(95)
		}
		pid, err := strconv.ParseUint(strings.TrimSpace(string(b)), 10, 32)
		if err != nil {
			os.Exit(96)
		}
		h, err := windows.OpenProcess(windows.SYNCHRONIZE, false, uint32(pid))
		if err != nil {
			os.Exit(97)
		}
		status, err := windows.WaitForSingleObject(h, 0)
		windows.CloseHandle(h)
		if err != nil || status != uint32(windows.WAIT_TIMEOUT) {
			os.Exit(98)
		}
		fmt.Println("CTM_CHILD_LIVE", pid)
		os.Exit(23)
	default:
		os.Exit(99)
	}
}
