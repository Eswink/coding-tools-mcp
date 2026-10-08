//go:build windows && !fixture

package main

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"

	"github.com/Microsoft/go-winio"
	"github.com/Microsoft/hcsshim/internal/gcs/prot"
)

func TestPolicyServiceInventory(t *testing.T) {
	ids := initialPolicyServices()
	if len(ids) != 7 || ids[0].String() != "acef5661-84a1-4e44-856b-6245e69f4620" || prot.LinuxGcsVsockPort != 0x40000000 {
		t.Fatal("pinned GCS constants changed")
	}
	for i := 1; i < 7; i++ {
		if ids[i] != winio.VsockServiceID(0x40000000+uint32(i)) {
			t.Fatal("stdio port drift")
		}
	}
	o := buildOptions("test-owned")
	p, e := configurePolicy(o)
	if e != nil {
		t.Fatal(e)
	}
	if len(p.services) != 10 || len(o.AdditionalHyperVConfig) != 10 || len(p.result.Nonce) != 32 || !strings.HasPrefix(p.result.BrokerSID, "S-1-") {
		t.Fatal("policy inventory")
	}
	seen := map[string]bool{}
	for i, g := range p.services {
		id := g.String()
		if seen[id] {
			t.Fatal("duplicate service")
		}
		seen[id] = true
		c := o.AdditionalHyperVConfig[id]
		if c.Disabled || c.BindSecurityDescriptor != "D:P(A;;FA;;;"+p.result.BrokerSID+")" || c.ConnectSecurityDescriptor != denyHv || c.AllowWildcardBinds != (i >= 8) {
			t.Fatal("unexpected policy authority")
		}
	}
}
func TestPolicyFramesRejectAmbiguity(t *testing.T) {
	for _, b := range [][]byte{nil, []byte(`{"phase":"x","unknown":1}`), []byte(`{} {}`), bytes.Repeat([]byte("x"), policyFrameLimit+1)} {
		if decodePolicyFrame(b, new(policyRequest)) == nil {
			t.Fatal("accepted malformed/oversized frame")
		}
	}
	r := policyRequest{Phase: "positive", Nonce: strings.Repeat("a", 32), Services: []string{"a", "b", "c"}}
	b, e := json.Marshal(r)
	if e != nil {
		t.Fatal(e)
	}
	var round policyRequest
	if e = decodePolicyFrame(b, &round); e != nil || !validPolicyRequest(round, "positive", r.Nonce, r.Services) {
		t.Fatal("valid request lost")
	}
	for _, bad := range []policyRequest{{Phase: "negative", Nonce: r.Nonce, Services: r.Services}, {Phase: r.Phase, Nonce: "bad", Services: r.Services}, {Phase: r.Phase, Nonce: r.Nonce, Services: []string{"a", "b", "x"}}} {
		if validPolicyRequest(bad, r.Phase, r.Nonce, r.Services) {
			t.Fatal("sequence/identity mismatch accepted")
		}
	}
}
func TestPolicyDenialRequiresExplicitError(t *testing.T) {
	for _, code := range []uint32{10013, 10061} {
		if !policyDialDenied(dialObservation{ErrorCode: code}) {
			t.Fatal("explicit denial lost")
		}
	}
	for _, o := range []dialObservation{{}, {ErrorCode: 10060}, {ErrorCode: 10049}, {ErrorCode: 10061, Connected: true}, {ErrorCode: 10061, Echo: true}, {ErrorCode: 10061, CloseError: "close"}} {
		if policyDialDenied(o) {
			t.Fatal("timeout/route/success/cleanup counted as denial")
		}
	}
}
func TestPolicyMatrixRequiresAllControls(t *testing.T) {
	ids := []string{"a", "b", "c"}
	good := []dialObservation{{Service: "a", Connected: true, Echo: true}, {Service: "b", Connected: true, Echo: true}, {Service: "c", Connected: true, Echo: true}}
	if checkDialMatrix(good, ids, true) != nil {
		t.Fatal("positive matrix")
	}
	if checkDialMatrix(good[:2], ids, true) == nil || checkDialMatrix(good, ids, false) == nil {
		t.Fatal("missing/bypassed matrix passed")
	}
	good[2].CloseError = "failed"
	if checkDialMatrix(good, ids, true) == nil {
		t.Fatal("close failure erased")
	}
	denied := []dialObservation{{Service: "a", ErrorCode: 10013}, {Service: "b", ErrorCode: 10061}, {Service: "c", ErrorCode: 10061}}
	if checkDialMatrix(denied, ids, false) != nil {
		t.Fatal("explicit negative matrix")
	}
	denied[1].Service = "other"
	if checkDialMatrix(denied, ids, false) == nil {
		t.Fatal("foreign service accepted")
	}
}
func TestPolicyFailureCannotAdmit(t *testing.T) {
	r := report{RuntimePassed: true, TerminateOK: true, WholeVMExited: true, ExitOK: true, CloseOK: true}
	r.record("policy", checkDialMatrix(nil, []string{"a", "b", "c"}, false))
	if complete(r) || r.NetworkDenied || r.WorkspaceIntegrated || r.ProductionAdmission {
		t.Fatal("policy failure overwritten or production enabled")
	}
}
