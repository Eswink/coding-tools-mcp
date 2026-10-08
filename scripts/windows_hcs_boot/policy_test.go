//go:build windows && !fixture

package main

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"

	"github.com/Microsoft/go-winio"
	"github.com/Microsoft/go-winio/pkg/guid"
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
	ids = make([]guid.GUID, 5)
	for i := range ids {
		g, e := guid.NewV4()
		if e != nil {
			t.Fatal(e)
		}
		ids[i] = g
	}
	for _, control := range []bool{true, false} {
		o := buildOptions("test-owned")
		p, e := configurePolicy(o, ids, control)
		if e != nil {
			t.Fatal(e)
		}
		want := 7
		if control {
			want = 12
		}
		if len(p.services) != 7 || len(o.AdditionalHyperVConfig) != want || len(p.result.Nonce) != 32 || !strings.HasPrefix(p.result.BrokerSID, "S-1-") {
			t.Fatal("static policy inventory")
		}
		allow := "D:P(A;;FA;;;" + p.result.BrokerSID + ")"
		for _, g := range p.services {
			c := o.AdditionalHyperVConfig[g.String()]
			if c.Disabled || c.BindSecurityDescriptor != allow || c.ConnectSecurityDescriptor != denyHv || c.AllowWildcardBinds {
				t.Fatal("broker policy authority")
			}
		}
		for i, g := range ids {
			c, found := o.AdditionalHyperVConfig[g.String()]
			if found != control {
				t.Fatal("restricted canary entry exists")
			}
			if !control {
				continue
			}
			connect := denyHv
			if i == 4 {
				connect = allow
			}
			if c.Disabled || c.BindSecurityDescriptor != allow || c.ConnectSecurityDescriptor != connect || c.AllowWildcardBinds != (i < 4) {
				t.Fatal("control permission inventory")
			}
		}
	}
}

func TestPolicyFramesRejectAmbiguity(t *testing.T) {
	for _, b := range [][]byte{nil, []byte(`{"phase":"x","unknown":1}`), []byte(`{} {}`), bytes.Repeat([]byte("x"), policyFrameLimit+1)} {
		if decodePolicyFrame(b, new(policyRequest)) == nil {
			t.Fatal("accepted malformed/oversized frame")
		}
	}
	r := policyRequest{Phase: "positive", Nonce: strings.Repeat("a", 32), Services: []string{"a", "b", "c", "d", "e"}}
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
	ids := []string{"a", "b", "c", "d"}
	good := []dialObservation{{Service: "a", Connected: true, Echo: true}, {Service: "b", Connected: true, Echo: true}, {Service: "c", Connected: true, Echo: true}, {Service: "d", Connected: true, Echo: true}}
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
	denied := []dialObservation{{Service: "a", ErrorCode: 10013}, {Service: "b", ErrorCode: 10061}, {Service: "c", ErrorCode: 10061}, {Service: "d", ErrorCode: 10061}}
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

func TestRegistrationOwnershipRejectsChanges(t *testing.T) {
	marker := "ctm-static-hvs:" + strings.Repeat("b", 32)
	if !registrationMatches(1, 0, 1, marker, marker) {
		t.Fatal("own marker rejected")
	}
	for _, x := range []struct {
		values, children, kind uint32
		value                  string
	}{{0, 0, 1, marker}, {2, 0, 1, marker}, {1, 1, 1, marker}, {1, 0, 2, marker}, {1, 0, 1, marker + "changed"}} {
		if registrationMatches(x.values, x.children, x.kind, x.value, marker) {
			t.Fatal("unexpected registry content accepted")
		}
	}
	if registrationMatches(1, 0, 1, "wrong", "wrong") {
		t.Fatal("unowned marker accepted")
	}
}
func TestStaticSecondVMRequiresCompleteFirst(t *testing.T) {
	r := report{TerminateOK: true, WholeVMExited: true, ExitOK: true, CloseOK: true, Policy: &policyResult{Profile: "control", MatrixPassed: true, SessionExited: true, CleanupOK: true}}
	if !staticProfileComplete(r) || r.RuntimePassed {
		t.Fatal("control completion or runtime classification")
	}
	for _, change := range []func(*report){func(r *report) { r.TerminateOK = false }, func(r *report) { r.WholeVMExited = false }, func(r *report) { r.ExitOK = false }, func(r *report) { r.CloseOK = false }, func(r *report) { r.Errors = []string{"failure"} }, func(r *report) { r.Policy.MatrixPassed = false }, func(r *report) { r.Policy.SessionExited = false }, func(r *report) { r.Policy.CleanupOK = false }} {
		copy := r
		policy := *r.Policy
		copy.Policy = &policy
		change(&copy)
		if staticProfileComplete(copy) {
			t.Fatal("incomplete first profile allowed second VM")
		}
	}
	r.Policy.Profile = "restricted"
	if staticProfileComplete(r) {
		t.Fatal("unrun stock runtime accepted")
	}
	r.RuntimePassed = true
	if !staticProfileComplete(r) {
		t.Fatal("complete restricted profile rejected")
	}
}
