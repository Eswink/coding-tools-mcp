//go:build windows && !fixture

package main

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/Microsoft/go-winio"
	"github.com/Microsoft/go-winio/pkg/guid"
	"github.com/Microsoft/hcsshim/internal/cow"
	"github.com/Microsoft/hcsshim/internal/gcs/prot"
	hcsschema "github.com/Microsoft/hcsshim/internal/hcs/schema2"
	"github.com/Microsoft/hcsshim/internal/uvm"
	"golang.org/x/sys/windows"
)

const denyHv = "D:P(D;;FA;;;WD)"

type bindObservation struct {
	Service   string `json:"service"`
	ErrorCode uint32 `json:"error_code"`
	Error     string `json:"error"`
	Denied    bool   `json:"denied"`
}
type policyResult struct {
	ExclusiveBindVerified bool     `json:"exclusive_bind_positive_control"`
	Updated               []string `json:"completed_service_updates"`
	BrokerSID             string   `json:"broker_sid"`
	Nonce                 string   `json:"nonce"`
	Allowed               []string `json:"initial_admitted_services"`
	Canaries              []string `json:"owned_canary_services"`
	ListenerRelease       []string `json:"released_listener_rebind_receipts"`
	Before, After         []dialObservation
	Binds                 []bindObservation `json:"new_exact_bind_observations"`
	Sealed                bool              `json:"all_descriptor_updates_completed"`
	MatrixPassed          bool              `json:"bounded_matrix_passed"`
	SessionExited         bool              `json:"supervisor_exited"`
	CleanupOK             bool              `json:"owned_endpoint_cleanup_ok"`
}
type ownedCanary struct {
	l        net.Listener
	nonce    string
	done     chan error
	mu       sync.Mutex
	closed   bool
	receipts int
}

func (c *ownedCanary) serve() {
	var err error
	defer func() { c.done <- err }()
	for {
		conn, e := c.l.Accept()
		if e != nil {
			c.mu.Lock()
			closing := c.closed
			c.mu.Unlock()
			if !closing {
				err = errors.Join(err, e)
			}
			return
		}
		e = conn.SetDeadline(time.Now().Add(2 * time.Second))
		b := make([]byte, len(c.nonce))
		if e == nil {
			_, e = io.ReadFull(conn, b)
		}
		if e == nil && string(b) != c.nonce {
			e = errors.New("unexpected canary nonce")
		}
		if e == nil {
			_, e = conn.Write(b)
		}
		e = errors.Join(e, conn.Close())
		err = errors.Join(err, e)
		c.mu.Lock()
		c.receipts++
		n := c.receipts
		c.mu.Unlock()
		if n > 2 {
			return
		}
	}
}
func (c *ownedCanary) close() error {
	c.mu.Lock()
	c.closed = true
	c.mu.Unlock()
	e := c.l.Close()
	select {
	case x := <-c.done:
		return errors.Join(e, x)
	case <-time.After(5 * time.Second):
		return errors.Join(e, errors.New("owned canary task not joined"))
	}
}

type hvPolicy struct {
	cleanupErr error
	result     *policyResult
	services   []guid.GUID
	canaries   []*ownedCanary
	session    *policySession
}

func initialPolicyServices() []guid.GUID {
	ids := []guid.GUID{prot.WindowsGcsHvsockServiceID}
	for p := uint32(prot.LinuxGcsVsockPort + 1); p <= prot.LinuxGcsVsockPort+6; p++ {
		ids = append(ids, winio.VsockServiceID(p))
	}
	return ids
}
func configurePolicy(o *uvm.OptionsWCOW) (*hvPolicy, error) {
	user, e := windows.GetCurrentProcessToken().GetTokenUser()
	if e != nil {
		return nil, e
	}
	n, e := guid.NewV4()
	if e != nil {
		return nil, e
	}
	r := &policyResult{BrokerSID: user.User.Sid.String(), Nonce: strings.ReplaceAll(n.String(), "-", "")}
	h := &hvPolicy{result: r, services: initialPolicyServices()}
	allow := "D:P(A;;FA;;;" + r.BrokerSID + ")"
	for i := 0; i < 3; i++ {
		g, e := guid.NewV4()
		if e != nil {
			return nil, e
		}
		h.services = append(h.services, g)
		r.Canaries = append(r.Canaries, g.String())
	}
	for i, id := range h.services {
		r.Allowed = append(r.Allowed, id.String())
		o.AdditionalHyperVConfig[id.String()] = hcsschema.HvSocketServiceConfig{BindSecurityDescriptor: allow, ConnectSecurityDescriptor: denyHv, AllowWildcardBinds: i >= 8}
	}
	return h, nil
}
func (h *hvPolicy) openCanaries(vm *uvm.UtilityVM) error {
	scopes := []guid.GUID{vm.RuntimeID(), winio.HvsockGUIDWildcard(), winio.HvsockGUIDChildren()}
	for i, scope := range scopes {
		l, e := winio.ListenHvsock(&winio.HvsockAddr{VMID: scope, ServiceID: h.services[i+7]})
		if e != nil {
			return e
		}
		c := &ownedCanary{l: l, nonce: h.result.Nonce, done: make(chan error, 1)}
		h.canaries = append(h.canaries, c)
		go c.serve()
	}
	return nil
}
func (h *hvPolicy) close() error {
	e := h.cleanupErr
	for _, c := range h.canaries {
		e = errors.Join(e, c.close())
	}
	e = errors.Join(e, h.session.close())
	h.result.CleanupOK = e == nil
	return e
}
func checkDialMatrix(got []dialObservation, ids []string, positive bool) error {
	if len(got) != 3 || len(ids) != 3 {
		return errors.New("canary inventory mismatch")
	}
	for i, o := range got {
		if o.Service != ids[i] {
			return errors.New("canary service mismatch")
		}
		if positive {
			if !o.Connected || !o.Echo || o.Error != "" || o.CloseError != "" {
				return fmt.Errorf("positive control failed: %s", o.Service)
			}
		} else if !policyDialDenied(o) {
			return fmt.Errorf("new connection denial not proven: %s", o.Service)
		}
	}
	return nil
}
func denyNewBind(vmID, service guid.GUID) (o bindObservation) {
	o.Service = service.String()
	l, e := winio.ListenHvsock(&winio.HvsockAddr{VMID: vmID, ServiceID: service})
	if e == nil {
		o.Error = "unexpected bind allowed"
		if x := l.Close(); x != nil {
			o.Error += "; close: " + x.Error()
		}
		return
	}
	o.Error = e.Error()
	var code syscall.Errno
	if errors.As(e, &code) {
		o.ErrorCode = uint32(code)
	}
	o.Denied = errors.Is(e, windows.WSAEACCES)
	return
}
func (h *hvPolicy) run(ctx context.Context, vm *uvm.UtilityVM, host cow.ProcessHost, r *report) (err error) {
	if err = h.openCanaries(vm); err != nil {
		return err
	}
	duplicate, e := winio.ListenHvsock(&winio.HvsockAddr{VMID: vm.RuntimeID(), ServiceID: h.services[7]})
	if e == nil {
		return errors.Join(errors.New("active listener allowed duplicate bind; release proof invalid"), duplicate.Close())
	}
	if !errors.Is(e, windows.WSAEADDRINUSE) {
		return fmt.Errorf("duplicate bind control: %w", e)
	}
	h.result.ExclusiveBindVerified = true
	h.session, err = startPolicySession(ctx, host)
	if err != nil {
		return err
	}
	pos, err := h.session.exchange(ctx, "positive", h.result.Nonce, h.result.Canaries)
	h.result.Before = pos.Dials
	if err != nil {
		return err
	}
	if err = checkDialMatrix(pos.Dials, h.result.Canaries, true); err != nil {
		return err
	}
	// Rebinding the identical addresses after all three IO receipts verifies released listeners.
	for _, id := range h.services[:7] {
		l, e := winio.ListenHvsock(&winio.HvsockAddr{VMID: vm.RuntimeID(), ServiceID: id})
		if e != nil {
			return fmt.Errorf("initial listener not released: %w", e)
		}
		if e = l.Close(); e != nil {
			return e
		}
		h.result.ListenerRelease = append(h.result.ListenerRelease, id.String())
	}
	for _, id := range h.services {
		e := vm.UpdateHvSocketService(ctx, id.String(), &hcsschema.HvSocketServiceConfig{BindSecurityDescriptor: denyHv, ConnectSecurityDescriptor: denyHv, AllowWildcardBinds: false, Disabled: false})
		if e != nil {
			return fmt.Errorf("descriptor transition %s: %w", id, e)
		}
		h.result.Updated = append(h.result.Updated, id.String())
	}
	h.result.Sealed = true
	neg, e := h.session.exchange(ctx, "negative", h.result.Nonce, h.result.Canaries)
	h.result.After = neg.Dials
	err = errors.Join(e, checkDialMatrix(neg.Dials, h.result.Canaries, false))
	for _, c := range h.canaries {
		h.cleanupErr = errors.Join(h.cleanupErr, c.close())
	}
	h.canaries = nil
	err = errors.Join(err, h.cleanupErr)
	fresh, e := guid.NewV4()
	if e != nil {
		return errors.Join(err, e)
	}
	for _, id := range append(append([]guid.GUID(nil), h.services...), fresh) {
		o := denyNewBind(vm.RuntimeID(), id)
		h.result.Binds = append(h.result.Binds, o)
		if !o.Denied {
			err = errors.Join(err, fmt.Errorf("exact bind denial absent: %s", o.Service))
		}
	}
	if err != nil {
		return err
	}
	h.result.MatrixPassed = true
	runtimes, e := h.session.exchange(ctx, "runtimes", h.result.Nonce, h.result.Canaries)
	r.Cases = append(r.Cases, runtimes.Cases...)
	if e != nil {
		return e
	}
	if len(runtimes.Cases) != 6 {
		return errors.New("post-seal runtime inventory")
	}
	for _, c := range runtimes.Cases {
		if !c.Passed {
			return fmt.Errorf("post-seal runtime failed: %s", c.Name)
		}
	}
	if _, e = h.session.exchange(ctx, "finish", h.result.Nonce, h.result.Canaries); e != nil {
		return e
	}
	if e = h.session.finish(ctx); e != nil {
		return e
	}
	h.result.SessionExited = true
	return nil
}
