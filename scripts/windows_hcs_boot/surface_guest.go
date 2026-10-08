//go:build windows

package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"time"

	"golang.org/x/sys/windows"
)

type transferInput struct {
	Nonce    string `json:"nonce"`
	Data     []byte `json:"data"`
	InputSHA string `json:"input_sha256"`
}
type socketObservation struct {
	Name       string `json:"name"`
	Endpoint   string `json:"guest_owned_endpoint,omitempty"`
	Created    bool   `json:"created"`
	Closed     bool   `json:"closed"`
	Bytes      int    `json:"nonce_bytes"`
	Error      string `json:"error"`
	CloseError string `json:"close_error"`
}
type transferReply struct {
	Marker      string              `json:"marker"`
	Nonce       string              `json:"nonce"`
	InputSHA    string              `json:"input_sha256"`
	Data        []byte              `json:"data"`
	OutputSHA   string              `json:"output_sha256"`
	Allocations []socketObservation `json:"allocations"`
	Peers       []socketObservation `json:"peers"`
}

var socketInventory = []struct {
	name                   string
	family, kind, protocol int
}{
	{"ipv4-tcp", windows.AF_INET, windows.SOCK_STREAM, windows.IPPROTO_TCP},
	{"ipv4-udp", windows.AF_INET, windows.SOCK_DGRAM, windows.IPPROTO_UDP},
	{"ipv6-tcp", windows.AF_INET6, windows.SOCK_STREAM, windows.IPPROTO_TCP},
	{"ipv6-udp", windows.AF_INET6, windows.SOCK_DGRAM, windows.IPPROTO_UDP},
	{"unix-stream", windows.AF_UNIX, windows.SOCK_STREAM, 0},
	{"hyperv-allocation-only", 34, windows.SOCK_STREAM, 1},
}

func fixtureHash(b []byte) string { s := sha256.Sum256(b); return hex.EncodeToString(s[:]) }
func fixtureError(e error) string {
	if e != nil {
		return e.Error()
	}
	return ""
}
func decodeFixture(data []byte, max int, target any) error {
	if len(data) > max {
		return errors.New("fixture envelope too large")
	}
	d := json.NewDecoder(bytes.NewReader(data))
	d.DisallowUnknownFields()
	if e := d.Decode(target); e != nil {
		return e
	}
	if d.Decode(new(any)) != io.EOF {
		return errors.New("extra fixture envelope")
	}
	return nil
}
func observeLocalPeer(network, address, nonce string) (o socketObservation) {
	o.Name = network
	l, e := net.Listen(network, address)
	if e != nil {
		o.Error = e.Error()
		return
	}
	o.Created = true
	o.Endpoint = l.Addr().String()
	closers := []io.Closer{l}
	defer func() {
		var err error
		for _, c := range closers {
			err = errors.Join(err, c.Close())
		}
		o.Closed = err == nil
		o.CloseError = fixtureError(err)
	}()
	deadline := time.Now().Add(time.Second)
	if d, ok := l.(interface{ SetDeadline(time.Time) error }); !ok {
		o.Error = "listener has no deadline"
		return
	} else if e = d.SetDeadline(deadline); e != nil {
		o.Error = e.Error()
		return
	}
	client, e := net.DialTimeout(network, l.Addr().String(), time.Second)
	if e != nil {
		o.Error = e.Error()
		return
	}
	closers = append(closers, client)
	if e = client.SetDeadline(deadline); e != nil {
		o.Error = e.Error()
		return
	}
	server, e := l.Accept()
	if e != nil {
		o.Error = e.Error()
		return
	}
	closers = append(closers, server)
	if e = server.SetDeadline(deadline); e != nil {
		o.Error = e.Error()
		return
	}
	if n, e := client.Write([]byte(nonce)); e != nil || n != len(nonce) {
		o.Error = fmt.Sprintf("nonce write %d: %v", n, e)
		return
	}
	b := make([]byte, len(nonce))
	if _, e = io.ReadFull(server, b); e != nil || string(b) != nonce {
		o.Error = fmt.Sprintf("nonce read: %v", e)
		return
	}
	if n, e := server.Write(b); e != nil || n != len(b) {
		o.Error = fmt.Sprintf("ack write %d: %v", n, e)
		return
	}
	if _, e = io.ReadFull(client, b); e != nil || string(b) != nonce {
		o.Error = fmt.Sprintf("ack read: %v", e)
		return
	}
	o.Bytes = len(nonce) * 2
	return
}
func runSurfaceFixture() error {
	b, e := io.ReadAll(io.LimitReader(os.Stdin, 4097))
	var in transferInput
	if e = errors.Join(e, decodeFixture(b, 4096, &in)); e != nil {
		return e
	}
	n, e := hex.DecodeString(in.Nonce)
	if e != nil || len(n) != 16 || len(in.Data) == 0 || len(in.Data) > 1024 || fixtureHash(in.Data) != in.InputSHA {
		return errors.New("invalid fixed fixture input")
	}
	if e = os.WriteFile("surface-input.bin", in.Data, 0600); e != nil {
		return e
	}
	input, e := os.ReadFile("surface-input.bin")
	if e != nil || fixtureHash(input) != in.InputSHA {
		return errors.New("guest input roundtrip mismatch")
	}
	output := bytes.ToUpper(input)
	if e = os.WriteFile("surface-output.bin", output, 0600); e != nil {
		return e
	}
	output, e = os.ReadFile("surface-output.bin")
	if e != nil {
		return e
	}
	out := transferReply{Marker: "CTM_SURFACE_ENTRY", Nonce: in.Nonce, InputSHA: in.InputSHA, Data: output, OutputSHA: fixtureHash(output)}
	var wsa windows.WSAData
	if e = windows.WSAStartup(0x202, &wsa); e != nil {
		return e
	}
	for _, s := range socketInventory {
		o := socketObservation{Name: s.name}
		h, err := windows.Socket(s.family, s.kind, s.protocol)
		o.Error = fixtureError(err)
		if err == nil {
			o.Created = true
			err = windows.Closesocket(h)
			o.Closed = err == nil
			o.CloseError = fixtureError(err)
		}
		out.Allocations = append(out.Allocations, o)
	}
	if e = windows.WSACleanup(); e != nil {
		return e
	}
	out.Peers = append(out.Peers, observeLocalPeer("tcp4", "127.0.0.1:0", in.Nonce))
	out.Peers = append(out.Peers, observeLocalPeer("tcp6", "[::1]:0", in.Nonce))
	out.Peers = append(out.Peers, observeLocalPeer("unix", filepath.Join(".", "surface-"+in.Nonce+".sock"), in.Nonce))
	b, e = json.Marshal(out)
	if e != nil {
		return e
	}
	if len(b) > 8192 {
		return errors.New("guest reply exceeds bound")
	}
	_, e = fmt.Fprintln(os.Stdout, string(b))
	return e
}
