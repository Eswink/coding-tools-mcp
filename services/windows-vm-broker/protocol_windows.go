//go:build windows

package main

import (
	"bytes"
	"encoding/binary"
	"encoding/json"
	"errors"
	"io"
	"reflect"
	"regexp"
	"strconv"
	"unicode/utf8"
)

const frameLimit = 65536
const aggregateLimit = 1048576

var buildSource string

type Request struct {
	Version int    `json:"version"`
	Source  string `json:"source"`
	Session string `json:"session"`
	Seq     uint64 `json:"seq"`
	Op      string `json:"op"`
	Fixture string `json:"fixture"`
}
type Case struct {
	Name     string `json:"name"`
	Stdout   string `json:"stdout"`
	Stderr   string `json:"stderr"`
	ExitCode int    `json:"exit_code"`
	Passed   bool   `json:"passed"`
}
type GuestResult struct {
	Cases        []Case `json:"cases"`
	InputSHA256  string `json:"input_sha256"`
	OutputSHA256 string `json:"output_sha256"`
	DataBase64   string `json:"data_base64"`
	ChildAlive   bool   `json:"child_alive"`
}
type Cleanup struct {
	TerminateOK          bool     `json:"terminate_ok"`
	WholeVMExited        bool     `json:"whole_vm_exited"`
	ExitOK               bool     `json:"exit_ok"`
	CloseOK              bool     `json:"close_ok"`
	GuestIOJoined        bool     `json:"guest_io_joined"`
	Quarantine           string   `json:"quarantine"`
	InputSHA256          string   `json:"input_sha256"`
	OutputSHA256         string   `json:"output_sha256"`
	OwnedDataRetained    bool     `json:"owned_data_retained"`
	NetworkDenialProven  bool     `json:"network_denial_proven"`
	WorkspaceIntegration bool     `json:"workspace_integration"`
	ProductionAdmission  bool     `json:"production_admission"`
	Errors               []string `json:"errors"`
}
type Event struct {
	Version   int          `json:"version"`
	Source    string       `json:"source"`
	Session   string       `json:"session"`
	Seq       uint64       `json:"seq"`
	Kind      string       `json:"kind"`
	VMID      string       `json:"vm_id"`
	RuntimeID string       `json:"runtime_id"`
	Guest     *GuestResult `json:"guest"`
	Cleanup   *Cleanup     `json:"cleanup"`
	Error     string       `json:"error"`
}

// The first pass preserves duplicate/presence information before typed decoding.
func scanJSON(d *json.Decoder, t reflect.Type, depth int) error {
	tok, e := d.Token()
	if e != nil {
		return e
	}
	if tok == nil {
		if t != nil && t.Kind() != reflect.Pointer && t.Kind() != reflect.Interface {
			return errors.New("required non-null value")
		}
		return nil
	}
	for t != nil && t.Kind() == reflect.Pointer {
		t = t.Elem()
	}
	delim, nested := tok.(json.Delim)
	if !nested {
		return nil
	}
	if depth >= 8 {
		return errors.New("JSON depth bound")
	}
	switch delim {
	case '{':
		seen := map[string]bool{}
		fields := map[string]reflect.Type{}
		if t != nil && t.Kind() == reflect.Struct {
			for i := 0; i < t.NumField(); i++ {
				f := t.Field(i)
				fields[f.Tag.Get("json")] = f.Type
			}
		}
		for d.More() {
			k, e := d.Token()
			if e != nil {
				return e
			}
			key, ok := k.(string)
			if !ok || seen[key] {
				return errors.New("duplicate or invalid key")
			}
			seen[key] = true
			if t != nil && t.Kind() == reflect.Struct {
				if _, ok := fields[key]; !ok {
					return errors.New("unknown exact field: " + key)
				}
			}
			if e = scanJSON(d, fields[key], depth+1); e != nil {
				return e
			}
		}
		for key := range fields {
			if !seen[key] {
				return errors.New("required field missing: " + key)
			}
		}
	case '[':
		var elem reflect.Type
		if t != nil && t.Kind() == reflect.Slice {
			elem = t.Elem()
		}
		for d.More() {
			if e = scanJSON(d, elem, depth+1); e != nil {
				return e
			}
		}
	default:
		return errors.New("unexpected JSON delimiter")
	}
	_, e = d.Token()
	return e
}
func decodeStrict(b []byte, v any) error {
	if len(b) == 0 || len(b) > frameLimit || !utf8.Valid(b) || !validSurrogates(b) {
		return errors.New("JSON frame bound")
	}
	t := reflect.TypeOf(v)
	if t == nil || t.Kind() != reflect.Pointer {
		return errors.New("decode target")
	}
	d := json.NewDecoder(bytes.NewReader(b))
	if e := scanJSON(d, t.Elem(), 0); e != nil {
		return e
	}
	if _, e := d.Token(); e != io.EOF {
		return errors.New("trailing JSON")
	}
	d = json.NewDecoder(bytes.NewReader(b))
	d.DisallowUnknownFields()
	return d.Decode(v)
}
func readFrame(r io.Reader, total *int, v any) error {
	var b [4]byte
	if _, e := io.ReadFull(r, b[:]); e != nil {
		return e
	}
	n := int(binary.LittleEndian.Uint32(b[:]))
	if n < 1 || n > frameLimit || *total+4+n > aggregateLimit {
		return errors.New("frame/aggregate bound")
	}
	*total += 4 + n
	p := make([]byte, n)
	if _, e := io.ReadFull(r, p); e != nil {
		return e
	}
	return decodeStrict(p, v)
}
func writeFrame(w io.Writer, total *int, v any) error {
	p, e := json.Marshal(v)
	if e != nil {
		return e
	}
	if len(p) < 1 || len(p) > frameLimit || *total+4+len(p) > aggregateLimit {
		return errors.New("write frame bound")
	}
	*total += 4 + len(p)
	var b [4]byte
	binary.LittleEndian.PutUint32(b[:], uint32(len(p)))
	for _, p := range [][]byte{b[:], p} {
		n, e := w.Write(p)
		if e != nil {
			return e
		}
		if n != len(p) {
			return io.ErrShortWrite
		}
	}
	return nil
}

type GuestRequest struct {
	Request     Request `json:"request"`
	DataBase64  string  `json:"data_base64"`
	InputSHA256 string  `json:"input_sha256"`
}

const outputLimit = 65536

type boundedOutput struct {
	buffer   bytes.Buffer
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

var wireSource = regexp.MustCompile(`^[0-9a-f]{40}$`)
var wireSession = regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`)

func validateRequest(r Request, source, session string, seq uint64, op string) error {
	if r.Version != 1 || !wireSource.MatchString(source) || r.Source != source || !wireSession.MatchString(session) || r.Session != session || r.Seq != seq || r.Op != op || (r.Fixture != "runtimes" && r.Fixture != "live-child") {
		return errors.New("request identity/sequence/operation")
	}
	return nil
}

// encoding/json repairs lone surrogate escapes; reject them before that lossy step.
func validSurrogates(b []byte) bool {
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
