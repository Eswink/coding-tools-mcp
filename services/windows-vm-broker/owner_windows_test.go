//go:build windows && !guest

package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Microsoft/go-winio"
	"github.com/Microsoft/hcsshim/internal/cow"
	"github.com/Microsoft/hcsshim/internal/gcs/prot"
)

const testSource = "0123456789abcdef0123456789abcdef01234567"
const testSession = "12345678-1234-4234-8234-123456789abc"

func encoded(t *testing.T, value any) []byte {
	t.Helper()
	b, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func cleanReceipt() Cleanup {
	return Cleanup{TerminateOK: true, WholeVMExited: true, ExitOK: true, CloseOK: true,
		GuestIOJoined: true, OwnedDataRetained: true, Quarantine: "written", InputSHA256: strings.Repeat("a", 64),
		OutputSHA256: strings.Repeat("b", 64), Errors: []string{}}
}

func runtimeGuest() GuestResult {
	input := []byte("ctm-synthetic:" + testSession)
	output := bytes.ToUpper(input)
	inHash, outHash := sha256.Sum256(input), sha256.Sum256(output)
	return GuestResult{Cases: []Case{}, InputSHA256: hex.EncodeToString(inHash[:]),
		OutputSHA256: hex.EncodeToString(outHash[:]), DataBase64: base64.StdEncoding.EncodeToString(output)}
}
func TestWireRoundTrip(t *testing.T) {
	want := Request{Version: 1, Source: testSource, Session: testSession, Seq: 0,
		Op: "prepare", Fixture: "runtimes"}
	var transport bytes.Buffer
	written, read := 0, 0
	if err := writeFrame(&transport, &written, want); err != nil {
		t.Fatal(err)
	}
	raw := append([]byte(nil), transport.Bytes()...)
	var got Request
	if err := readFrame(&transport, &read, &got); err != nil || got != want || read != written {
		t.Fatalf("roundtrip: got=%+v read=%d written=%d err=%v", got, read, written, err)
	}
	if err := readFrame(&transport, &read, &got); err != io.EOF {
		t.Fatalf("terminal EOF: %v", err)
	}
	read = aggregateLimit
	if readFrame(bytes.NewReader(raw), &read, &got) == nil {
		t.Fatal("reader aggregate overflow accepted")
	}
}
func TestStrictJSONRejectsAmbiguity(t *testing.T) {
	request := Request{Version: 1, Source: testSource, Session: testSession, Op: "prepare", Fixture: "runtimes"}
	base := string(encoded(t, request))
	for _, raw := range []string{
		strings.Replace(base, `"version":1`, `"version":1,"version":1`, 1),
		strings.Replace(base, `"version":1`, `"version":1,"unknown":0`, 1), base + `{}`,
		strings.Replace(base, `"version":1`, `"version":1,"Version":1`, 1),
		strings.Replace(base, testSource, string([]byte{0xff}), 1),
		strings.Replace(base, testSource, `\ud800`, 1), strings.Replace(base, testSource, `\udc00`, 1),
	} {
		var got Request
		if decodeStrict([]byte(raw), &got) == nil {
			t.Fatalf("accepted ambiguous request: %s", raw)
		}
	}
	guest := runtimeGuest()
	guest.Cases = []Case{{Name: "cmd", Stdout: "ok", Stderr: "", ExitCode: 0, Passed: true}}
	nested := strings.Replace(string(encoded(t, guest)), `"passed":true`, `"passed":true,"passed":false`, 1)
	if decodeStrict([]byte(nested), &GuestResult{}) == nil {
		t.Fatal("accepted duplicate nested field")
	}
	nilCases := runtimeGuest()
	nilCases.Cases = nil
	if decodeStrict(encoded(t, nilCases), &GuestResult{}) == nil {
		t.Fatal("accepted null cases list")
	}
	if decodeStrict(bytes.Replace(encoded(t, cleanReceipt()), []byte(`"errors":[]`), []byte(`"errors":null`), 1), &Cleanup{}) == nil {
		t.Fatal("accepted null errors list")
	}
	for _, value := range []any{request, Event{}, guest, guest.Cases[0], cleanReceipt()} {
		var fields map[string]json.RawMessage
		if err := json.Unmarshal(encoded(t, value), &fields); err != nil {
			t.Fatal(err)
		}
		for key, original := range fields {
			delete(fields, key)
			var target any
			switch value.(type) {
			case Request:
				target = &Request{}
			case Event:
				target = &Event{}
			case GuestResult:
				target = &GuestResult{}
			case Case:
				target = &Case{}
			case Cleanup:
				target = &Cleanup{}
			}
			if decodeStrict(encoded(t, fields), target) == nil {
				t.Fatalf("accepted missing %T.%s", value, key)
			}
			fields[key] = original
		}
	}
}
func TestFrameAndDepthBounds(t *testing.T) {
	var nested [1][1][1][1][1][1][1][1]int
	if err := decodeStrict([]byte(`[[[[[[[[0]]]]]]]]`), &nested); err != nil {
		t.Fatalf("depth eight rejected: %v", err)
	}
	if err := decodeStrict([]byte(`[[[[[[[[[0]]]]]]]]]`), &nested); err == nil || !strings.Contains(err.Error(), "depth") {
		t.Fatal("depth nine was not rejected by the depth guard")
	}
	for _, size := range []uint32{0, 65537, ^uint32(0)} {
		var prefix [4]byte
		binary.LittleEndian.PutUint32(prefix[:], size)
		total := 0
		if readFrame(bytes.NewReader(prefix[:]), &total, &Request{}) == nil {
			t.Fatalf("accepted invalid frame size %d", size)
		}
	}
	for _, raw := range [][]byte{{1}, {3, 0, 0, 0, '{'}} {
		total := 0
		if readFrame(bytes.NewReader(raw), &total, &Request{}) == nil {
			t.Fatal("accepted truncated frame")
		}
	}
	var transport bytes.Buffer
	total := 1 << 20
	if writeFrame(&transport, &total, Request{}) == nil || transport.Len() != 0 {
		t.Fatal("aggregate overflow wrote bytes")
	}
	total = 0
	if writeFrame(&transport, &total, strings.Repeat("x", 65536)) == nil {
		t.Fatal("oversized encoded frame accepted")
	}
}
func TestRequestBindings(t *testing.T) {
	good := Request{Version: 1, Source: testSource, Session: testSession, Seq: 3, Op: "start", Fixture: "runtimes"}
	if err := validateRequest(good, testSource, testSession, 3, "start"); err != nil {
		t.Fatal(err)
	}
	for _, mutate := range []func(*Request){
		func(r *Request) { r.Version = 2 }, func(r *Request) { r.Source = strings.Repeat("0", 40) },
		func(r *Request) { r.Session = "12345678-1234-4234-8234-123456789abd" },
		func(r *Request) { r.Session = strings.ToUpper(testSession) }, func(r *Request) { r.Seq-- },
		func(r *Request) { r.Seq++ }, func(r *Request) { r.Op = "finish" },
		func(r *Request) { r.Fixture = "arbitrary-command" },
	} {
		bad := good
		mutate(&bad)
		if validateRequest(bad, testSource, testSession, 3, "start") == nil {
			t.Fatalf("accepted mismatched request %+v", bad)
		}
	}
	for _, invalid := range []string{strings.Repeat("z", 36), strings.ToUpper(testSession)} {
		bad := good
		bad.Session = invalid
		if validateRequest(bad, testSource, invalid, 3, "start") == nil {
			t.Fatal("matching malformed session accepted")
		}
	}
	bad := good
	bad.Source = strings.Repeat("z", 40)
	if validateRequest(bad, bad.Source, testSession, 3, "start") == nil {
		t.Fatal("matching malformed source accepted")
	}
}
func TestGuestCannotForgeCleanup(t *testing.T) {
	for _, raw := range [][]byte{encoded(t, cleanReceipt()), []byte(`{"kind":"cleanup","whole_vm_exited":true}`)} {
		if decodeStrict(raw, &GuestResult{}) == nil {
			t.Fatal("host receipt accepted as guest data")
		}
	}
	root, err := newSyntheticRoot(t.TempDir(), testSession)
	if err != nil {
		t.Fatal(err)
	}
	defer root.close()
	guest := runtimeGuest()
	guest.DataBase64 = base64.StdEncoding.EncodeToString(encoded(t, cleanReceipt()))
	if root.acceptGuest(guest) == nil {
		t.Fatal("guest data manufactured host completion")
	}
}
func TestIndependentLifecycleProof(t *testing.T) {
	good := cleanReceipt()
	if !lifecycleComplete(good) || !completeCleanup(good, false) {
		t.Fatal("complete independent proof rejected")
	}
	for _, mutate := range []func(*Cleanup){
		func(c *Cleanup) { c.TerminateOK = false }, func(c *Cleanup) { c.WholeVMExited = false },
		func(c *Cleanup) { c.ExitOK = false }, func(c *Cleanup) { c.CloseOK = false },
		func(c *Cleanup) { c.GuestIOJoined = false }, func(c *Cleanup) { c.Errors = []string{"close failed"} },
		func(c *Cleanup) { c.OwnedDataRetained = false },
		func(c *Cleanup) { c.NetworkDenialProven = true }, func(c *Cleanup) { c.WorkspaceIntegration = true },
		func(c *Cleanup) { c.ProductionAdmission = true },
	} {
		bad := good
		mutate(&bad)
		if lifecycleComplete(bad) || completeCleanup(bad, false) {
			t.Fatalf("partial/error proof accepted %+v", bad)
		}
	}
	for _, quarantine := range []string{"withheld", "not-started", ""} {
		bad := good
		bad.Quarantine = quarantine
		if completeCleanup(bad, false) {
			t.Fatalf("normal completion accepted disposition %q", quarantine)
		}
	}
	checkGuestJoins(t)
}

type inertProcess struct {
	cow.Process
	waitErr            error
	halfclose, entered chan struct{}
	closed             sync.Once
}

func (p *inertProcess) Wait() error          { return p.waitErr }
func (*inertProcess) ExitCode() (int, error) { return 23, nil }
func (p *inertProcess) CloseStdin(context.Context) error {
	if p.halfclose != nil {
		close(p.entered)
		<-p.halfclose
	}
	return nil
}
func (*inertProcess) CloseStdout(context.Context) error { return nil }
func (*inertProcess) CloseStderr(context.Context) error { return nil }
func (p *inertProcess) Close() error {
	if p.halfclose != nil {
		p.closed.Do(func() { close(p.halfclose) })
	}
	return nil
}

type faultIO struct{ err error }

func (f faultIO) Read([]byte) (int, error)  { return 0, f.err }
func (f faultIO) Write([]byte) (int, error) { return 0, f.err }

func checkGuestJoins(t *testing.T) {
	t.Helper()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	faults := []error{errors.New("write"), errors.New("stdout"), errors.New("stderr"), errors.New("wait")}
	g := &guestProcess{p: &inertProcess{waitErr: faults[3]}, in: faultIO{faults[0]}, out: faultIO{faults[1]}, stderr: faultIO{faults[2]}}
	_ = g.bootstrap(ctx, strings.NewReader("fixed synthetic input"))
	joined, err := g.close()
	for _, fault := range faults {
		if !joined || !errors.Is(err, fault) {
			t.Fatalf("cancelled bootstrap lost %v: %v", fault, err)
		}
	}
	g = &guestProcess{p: &inertProcess{}, in: &bytes.Buffer{}, out: strings.NewReader(strings.Repeat("x", outputLimit+1)), stderr: strings.NewReader("")}
	_ = g.bootstrap(ctx, strings.NewReader("fixed synthetic input"))
	if joined, err = g.close(); !joined || err == nil {
		t.Fatal("cancelled bootstrap lost stdout overflow")
	}
	for _, malformed := range []bool{true, false} {
		var stream bytes.Buffer
		total := 0
		for _, value := range []GuestResult{{Cases: []Case{{Name: "ready", Passed: true}}}, runtimeGuest()} {
			if err := writeFrame(&stream, &total, value); err != nil {
				t.Fatal(err)
			}
		}
		if malformed {
			stream.Write([]byte{0, 0, 0, 0})
		} else if err := writeFrame(&stream, &total, runtimeGuest()); err != nil {
			t.Fatal(err)
		}
		g = &guestProcess{p: &inertProcess{}, out: &stream, stderr: strings.NewReader(""), waited: make(chan error, 1)}
		readCtx, stop := context.WithTimeout(context.Background(), time.Second)
		if err := g.startFrames(readCtx); err != nil {
			stop()
			t.Fatal(err)
		}
		if _, err := g.next(readCtx); err != nil {
			stop()
			t.Fatal(err)
		}
		_, frameErr := g.next(readCtx)
		joined, err := g.close()
		stop()
		if frameErr == nil || !joined || err == nil {
			t.Fatalf("extra/malformed frame lost at close: %v %v", frameErr, err)
		}
	}
	p := &inertProcess{halfclose: make(chan struct{}), entered: make(chan struct{})}
	g = &guestProcess{p: p}
	g.tasks.Add(1)
	go func() { defer g.tasks.Done(); g.writeErr = g.closeStdin() }()
	<-p.entered
	done := make(chan error, 1)
	go func() {
		joined, err := g.close()
		if !joined {
			err = errors.New("half-close not joined")
		}
		done <- err
	}()
	select {
	case err := <-done:
		if err != nil {
			t.Fatal(err)
		}
	case <-time.After(time.Second):
		_ = p.Close()
		<-done
		t.Fatal("stuck half-close prevented actual process close")
	}
}
func TestQuarantineRequiresWholeVM(t *testing.T) {
	root, err := newSyntheticRoot(t.TempDir(), testSession)
	if err != nil {
		t.Fatal(err)
	}
	defer root.close()
	if err := root.acceptGuest(runtimeGuest()); err != nil {
		t.Fatal(err)
	}
	cleanup := cleanReceipt()
	cleanup.Quarantine = "not-started"
	cleanup.WholeVMExited = false
	if root.finish(&cleanup, false) == nil || cleanup.Quarantine == "written" {
		t.Fatal("quarantine published before whole-VM completion")
	}
}
func TestSyntheticInputMutationRetainsData(t *testing.T) {
	directory := t.TempDir()
	root, err := newSyntheticRoot(directory, testSession)
	if err != nil {
		t.Fatal(err)
	}
	defer root.close()
	if len(root.data) > 1024 || string(root.data) != "ctm-synthetic:"+testSession {
		t.Fatal("synthetic input is not fixed and session-bound")
	}
	guest := runtimeGuest()
	guest.InputSHA256 = strings.Repeat("0", 64)
	if root.acceptGuest(guest) == nil {
		t.Fatal("accepted guest input hash mismatch")
	}
	guest = runtimeGuest()
	guest.OutputSHA256 = strings.Repeat("0", 64)
	if root.acceptGuest(guest) == nil {
		t.Fatal("accepted guest output hash mismatch")
	}
	if err := root.acceptGuest(runtimeGuest()); err != nil {
		t.Fatal(err)
	}
	input := filepath.Join(directory, "synthetic-source", "input.bin")
	if err := os.WriteFile(input, []byte("changed synthetic input"), 0600); err != nil {
		t.Fatal(err)
	}
	cleanup := cleanReceipt()
	cleanup.Quarantine = "not-started"
	if root.finish(&cleanup, false) == nil || !cleanup.OwnedDataRetained {
		t.Fatal("mutated input published output or discarded retained data")
	}
	if _, err := os.Stat(input); err != nil {
		t.Fatalf("uncertain input not retained: %v", err)
	}
}
func TestQuarantineRoundTripCreateNew(t *testing.T) {
	directory := t.TempDir()
	root, err := newSyntheticRoot(directory, testSession)
	if err != nil {
		t.Fatal(err)
	}
	defer root.close()
	guest := runtimeGuest()
	if err := root.acceptGuest(guest); err != nil {
		t.Fatal(err)
	}
	cleanup := cleanReceipt()
	if err := root.finish(&cleanup, false); err != nil || !completeCleanup(cleanup, false) {
		t.Fatalf("quarantine roundtrip: %+v %v", cleanup, err)
	}
	if cleanup.InputSHA256 != guest.InputSHA256 || cleanup.OutputSHA256 != guest.OutputSHA256 {
		t.Fatal("quarantine receipt not bound to transferred bytes")
	}
	returned, err := os.ReadFile(filepath.Join(directory, "quarantine", "returned.bin"))
	if err != nil || !bytes.Equal(returned, bytes.ToUpper(root.data)) {
		t.Fatalf("quarantine readback %q %v", returned, err)
	}
	if root.finish(&cleanup, false) == nil {
		t.Fatal("existing quarantine output overwritten")
	}
}
func TestCancellationWithholdsOutput(t *testing.T) {
	directory := t.TempDir()
	root, err := newSyntheticRoot(directory, testSession)
	if err != nil {
		t.Fatal(err)
	}
	defer root.close()
	if err := root.acceptGuest(runtimeGuest()); err != nil {
		t.Fatal(err)
	}
	cleanup := cleanReceipt()
	if err := root.finish(&cleanup, true); err != nil || cleanup.Quarantine != "withheld" {
		t.Fatalf("cancelled disposition %+v %v", cleanup, err)
	}
	if !completeCleanup(cleanup, true) || completeCleanup(cleanup, false) {
		t.Fatal("drained cancellation lost its cancellation disposition")
	}
	if _, err := os.Stat(filepath.Join(directory, "quarantine", "returned.bin")); !os.IsNotExist(err) {
		t.Fatalf("cancelled output was not withheld: %v", err)
	}
}
func TestOutputLimitIsStickyWhileReaderContinues(t *testing.T) {
	var output boundedOutput
	n, err := io.Copy(&output, strings.NewReader(strings.Repeat("x", outputLimit+1)))
	if err != nil || n != int64(outputLimit+1) || output.Len() != outputLimit || !output.overflow {
		t.Fatalf("bounded output did not drain: n=%d len=%d overflow=%v err=%v", n, output.Len(), output.overflow, err)
	}
	if n, err := output.Write([]byte("late bytes")); err != nil || n != 10 || !output.overflow || output.Len() != outputLimit {
		t.Fatal("overflow was not sticky or late data was retained")
	}
	var exact boundedOutput
	if _, err := io.Copy(&exact, strings.NewReader(strings.Repeat("y", outputLimit))); err != nil || exact.overflow || exact.Len() != outputLimit {
		t.Fatal("exact output bound was rejected")
	}
}

func TestFixedVMPolicyHasSevenServicesAndNoNIC(t *testing.T) {
	o := buildOptions(testSession)
	if o.ProcessorCount != 2 || o.MemorySizeInMB != 2048 || !o.NoWritableFileShares || !o.NoDirectMap || !o.NoInheritHostTimezone || o.NetworkConfigProxy != "" {
		t.Fatal("fixed resource or mapping policy changed")
	}
	spec := containerSpec([]string{"layer1", "layer0", "scratch"})
	if spec.Windows == nil || spec.Windows.Network != nil || spec.Linux != nil || len(spec.Mounts) != 0 {
		t.Fatal("container config acquired network or optional mappings")
	}
	const sid = "S-1-5-21-100-200-300-1000"
	if err := configureBrokerPolicy(o, sid); err != nil || len(o.AdditionalHyperVConfig) != 7 {
		t.Fatalf("service policy: %v", err)
	}
	ids := []string{prot.WindowsGcsHvsockServiceID.String()}
	for p := uint32(prot.LinuxGcsVsockPort + 1); p <= prot.LinuxGcsVsockPort+6; p++ {
		ids = append(ids, winio.VsockServiceID(p).String())
	}
	for _, id := range ids {
		entry, ok := o.AdditionalHyperVConfig[id]
		if !ok || entry.BindSecurityDescriptor != "D:P(A;;FA;;;"+sid+")" || entry.ConnectSecurityDescriptor != "D:P(D;;FA;;;WD)" {
			t.Fatalf("unexpected service authority for %s: %+v", id, entry)
		}
	}
	if configureBrokerPolicy(o, sid) == nil || configureBrokerPolicy(buildOptions(testSession), "invalid") == nil {
		t.Fatal("existing services or invalid SID accepted")
	}
}
