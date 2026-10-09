package main

// Private guest DATA contract, never native permission or a VM retirement seal.
import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"strconv"
	"strings"
	"unicode/utf8"
)

type guestMode uint8

const (
	guestFixtureMode             guestMode = 1
	guestWorkspaceMode           guestMode = 2
	guestWorkspaceControlMaximum           = 4096
	guestWorkspaceStderrMaximum            = 8192
)

func selectGuestMode(args []string) (guestMode, error) {
	if len(args) == 1 {
		switch args[0] {
		case "--guest":
			return guestFixtureMode, nil
		case "--guest-workspace":
			return guestWorkspaceMode, nil
		}
	}
	return 0, errors.New("guest mode rejected")
}

type workspaceGuestControl struct {
	Version       uint8  `json:"version"`
	Source        string `json:"source"`
	Session       string `json:"session"`
	Operation     string `json:"operation"`
	Binding       string `json:"binding"`
	InputSHA256   string `json:"input_sha256"`
	CommandSHA256 string `json:"command_sha256"`
	InputBytes    uint64 `json:"input_bytes"`
	InputLeaf     string `json:"input_leaf"`
	OutputLeaf    string `json:"output_leaf"`
	Command       string `json:"command"`
	Stdin         string `json:"stdin"`
	TimeoutMS     uint32 `json:"timeout_ms"`
}

func guestControlHex(s string, n int) bool {
	if len(s) != n {
		return false
	}
	for _, b := range []byte(s) {
		if !(b >= '0' && b <= '9' || b >= 'a' && b <= 'f') {
			return false
		}
	}
	return true
}
func guestControlUUID(s string) bool {
	return len(s) == 36 && s[8] == '-' && s[13] == '-' && s[18] == '-' && s[23] == '-' && s[14] == '4' && strings.ContainsRune("89ab", rune(s[19])) && guestControlHex(strings.ReplaceAll(s, "-", ""), 32)
}

// Deliberately narrow single-leaf mode. Host nested/Unicode paths are not inferred.
func guestControlLeaf(s string) bool {
	if s == "" || len(s) > 120 || s[0] == '.' || s[len(s)-1] == '.' {
		return false
	}
	for _, b := range []byte(s) {
		if !(b >= 'a' && b <= 'z' || b >= 'A' && b <= 'Z' || b >= '0' && b <= '9' || b == '.' || b == '_' || b == '-') {
			return false
		}
	}
	base := strings.ToUpper(strings.Split(s, ".")[0])
	switch base {
	case "CON", "PRN", "AUX", "NUL", "CLOCK$", "CONIN$", "CONOUT$":
		return false
	}
	for _, p := range []string{"COM", "LPT"} {
		if len(base) == 4 && strings.HasPrefix(base, p) && base[3] >= '1' && base[3] <= '9' {
			return false
		}
	}
	return true
}
func guestControlSurrogates(b []byte) bool {
	for i := 0; i < len(b); i++ {
		if b[i] != '\\' {
			continue
		}
		if i+1 >= len(b) {
			return false
		}
		if b[i+1] != 'u' {
			i++
			continue
		}
		if i+6 > len(b) {
			return false
		}
		n, e := strconv.ParseUint(string(b[i+2:i+6]), 16, 16)
		if e != nil {
			return false
		}
		if n >= 0xd800 && n <= 0xdbff {
			if i+12 > len(b) || b[i+6] != '\\' || b[i+7] != 'u' {
				return false
			}
			low, e := strconv.ParseUint(string(b[i+8:i+12]), 16, 16)
			if e != nil || low < 0xdc00 || low > 0xdfff {
				return false
			}
			i += 11
		} else {
			if n >= 0xdc00 && n <= 0xdfff {
				return false
			}
			i += 5
		}
	}
	return true
}
func parseWorkspaceGuestControl(raw []byte, source string) (workspaceGuestControl, [32]byte, error) {
	var c workspaceGuestControl
	reject := func() (workspaceGuestControl, [32]byte, error) {
		return c, [32]byte{}, errors.New("guest workspace control rejected")
	}
	if len(raw) == 0 || len(raw) > guestWorkspaceControlMaximum || !utf8.Valid(raw) || !guestControlSurrogates(raw) {
		return reject()
	}
	d := json.NewDecoder(bytes.NewReader(raw))
	tok, e := d.Token()
	if e != nil || tok != json.Delim('{') {
		return reject()
	}
	seen := map[string]bool{}
	for d.More() {
		key, e := d.Token()
		name, ok := key.(string)
		if e != nil || !ok || seen[name] {
			return reject()
		}
		switch name {
		case "version", "source", "session", "operation", "binding", "input_sha256", "command_sha256", "input_bytes", "input_leaf", "output_leaf", "command", "stdin", "timeout_ms":
		default:
			return reject()
		}
		var v json.RawMessage
		if d.Decode(&v) != nil || bytes.Equal(bytes.TrimSpace(v), []byte("null")) {
			return reject()
		}
		seen[name] = true
	}
	tok, e = d.Token()
	if e != nil || tok != json.Delim('}') || len(seen) != 13 {
		return reject()
	}
	var extra any
	if d.Decode(&extra) != io.EOF {
		return reject()
	}
	if json.Unmarshal(raw, &c) != nil || c.Version != 2 || !guestControlHex(source, 40) || source == strings.Repeat("0", 40) || c.Source != source || !guestControlUUID(c.Session) || !guestControlUUID(c.Operation) || !guestControlHex(c.Binding, 64) || c.Binding == strings.Repeat("0", 64) || !guestControlHex(c.InputSHA256, 64) || !guestControlHex(c.CommandSHA256, 64) || c.InputBytes > workspaceMaximum || !guestControlLeaf(c.InputLeaf) || !guestControlLeaf(c.OutputLeaf) || strings.EqualFold(c.InputLeaf, c.OutputLeaf) || c.Command == "" || len(c.Command) > 2048 || strings.ContainsRune(c.Command, 0) || len(c.Stdin) > 1024 || c.TimeoutMS == 0 || c.TimeoutMS > 30000 {
		return reject()
	}
	digest := sha256.Sum256([]byte(c.Command))
	if hex.EncodeToString(digest[:]) != c.CommandSHA256 {
		return reject()
	}
	return c, sha256.Sum256(raw), nil
}
func readWorkspaceGuestControl(r io.Reader, source string) (workspaceGuestControl, [32]byte, error) {
	var empty workspaceGuestControl
	var head [4]byte
	if r == nil {
		return empty, [32]byte{}, errors.New("guest control reader missing")
	}
	if _, e := io.ReadFull(r, head[:]); e != nil {
		return empty, [32]byte{}, errors.New("guest control truncated header")
	}
	n := binary.LittleEndian.Uint32(head[:])
	if n == 0 || n > guestWorkspaceControlMaximum {
		return empty, [32]byte{}, errors.New("guest control allocation bound")
	}
	raw := make([]byte, int(n))
	if _, e := io.ReadFull(r, raw); e != nil {
		return empty, [32]byte{}, errors.New("guest control truncated body")
	}
	return parseWorkspaceGuestControl(raw, source)
}
func (c workspaceGuestControl) inputManifest() workspaceStreamManifest {
	var binding, digest [32]byte
	b, _ := hex.DecodeString(c.Binding)
	copy(binding[:], b)
	b, _ = hex.DecodeString(c.InputSHA256)
	copy(digest[:], b)
	return workspaceStreamManifest{binding: binding, direction: 1, total: c.InputBytes, digest: digest}
}
