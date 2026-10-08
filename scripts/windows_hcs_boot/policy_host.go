//go:build windows && !fixture

package main

import (
	"context"
	"errors"
	"fmt"
	"github.com/Microsoft/go-winio"
	"github.com/Microsoft/go-winio/pkg/guid"
	"github.com/Microsoft/hcsshim/internal/cow"
	"github.com/Microsoft/hcsshim/internal/gcs/prot"
	hcsschema "github.com/Microsoft/hcsshim/internal/hcs/schema2"
	"github.com/Microsoft/hcsshim/internal/uvm"
	"golang.org/x/sys/windows"
	"golang.org/x/sys/windows/registry"
	"io"
	"net"
	"strings"
	"sync"
	"syscall"
	"time"
)

const denyHv = "D:P(D;;FA;;;WD)"
const registrationParent = `SOFTWARE\Microsoft\Windows NT\CurrentVersion\Virtualization\GuestCommunicationServices`

type bindObservation struct {
	Service   string `json:"service"`
	ErrorCode uint32 `json:"error_code"`
	Error     string `json:"error"`
	Denied    bool   `json:"denied"`
	Allowed   bool   `json:"allowed"`
	Closed    bool   `json:"closed"`
}
type policyResult struct {
	Profile               string            `json:"profile"`
	BrokerSID             string            `json:"broker_sid"`
	Nonce                 string            `json:"nonce"`
	Allowed               []string          `json:"initial_admitted_services"`
	Canaries              []string          `json:"owned_canary_services"`
	HostDials             []dialObservation `json:"guest_to_host"`
	HostConnect           dialObservation   `json:"host_to_guest"`
	GuestListener         *listenerReceipt  `json:"guest_listener"`
	HostAcceptCounts      []int             `json:"host_accept_counts"`
	Binds                 []bindObservation `json:"exact_bind_observations"`
	ListenerRelease       []string          `json:"released_listener_rebind_receipts"`
	ExclusiveBindVerified bool              `json:"exclusive_bind_positive_control"`
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
			err = errors.Join(err, errors.New("unexpected extra canary connection"))
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

type ownedRegistration struct {
	Name     string `json:"guid"`
	Marker   string `json:"marker"`
	Created  bool   `json:"created_new"`
	Verified bool   `json:"marker_verified"`
	Deleted  bool   `json:"absence_verified"`
	Retained bool   `json:"retained_or_uncertain"`
	key      registry.Key
}
type staticRegistry struct {
	parent registry.Key
	items  []*ownedRegistration
	ids    []guid.GUID
}

func inspectRegistration(k registry.Key, marker string) error {
	info, e := k.Stat()
	if e != nil {
		return e
	}
	value, kind, e := k.GetStringValue("ElementName")
	if e != nil {
		return e
	}
	if !registrationMatches(info.ValueCount, info.SubKeyCount, kind, value, marker) {
		return errors.New("registration ownership/content changed")
	}
	return nil
}
func newStaticRegistry() (*staticRegistry, error) {
	s := &staticRegistry{}
	seen := map[string]bool{}
	for i := 0; i < 5; i++ {
		g, e := guid.NewV4()
		if e != nil {
			return s, e
		}
		if seen[g.String()] {
			return s, errors.New("duplicate canary GUID")
		}
		seen[g.String()] = true
		s.ids = append(s.ids, g)
	}
	var e error
	s.parent, e = registry.OpenKey(registry.LOCAL_MACHINE, registrationParent, registry.READ|registry.WRITE)
	if e != nil {
		return s, e
	}
	for _, id := range s.ids[:2] {
		r := &ownedRegistration{Name: id.String(), Marker: "ctm-static-hvs:" + strings.ReplaceAll(id.String(), "-", "")}
		prior, e := registry.OpenKey(s.parent, r.Name, registry.READ)
		if e == nil {
			return s, errors.Join(errors.New("preexisting registration rejected"), prior.Close())
		}
		if !errors.Is(e, syscall.ERROR_FILE_NOT_FOUND) {
			return s, e
		}
		k, existing, e := registry.CreateKey(s.parent, r.Name, registry.READ|registry.WRITE)
		if e != nil {
			return s, e
		}
		if existing {
			return s, errors.Join(errors.New("registration create raced with existing key"), k.Close())
		}
		r.key = k
		r.Created = true
		s.items = append(s.items, r)
		if e = k.SetStringValue("ElementName", r.Marker); e != nil {
			return s, e
		}
		if e = inspectRegistration(k, r.Marker); e != nil {
			return s, e
		}
		r.Verified = true
	}
	return s, nil
}
func (s *staticRegistry) close(certain bool) (err error) {
	if s == nil {
		return nil
	}
	for _, r := range s.items {
		r.Retained = true
		if !certain {
			err = errors.Join(err, errors.New("uncertain VM lifetime: registration retained"), r.key.Close())
			continue
		}
		e := inspectRegistration(r.key, r.Marker)
		var fresh registry.Key
		if e == nil {
			fresh, e = registry.OpenKey(s.parent, r.Name, registry.READ)
		}
		if e == nil {
			e = inspectRegistration(fresh, r.Marker)
		}
		if e == nil {
			e = registry.DeleteKey(s.parent, r.Name)
		} // Exact child only, never recursive.
		if fresh != 0 {
			e = errors.Join(e, fresh.Close())
		}
		e = errors.Join(e, r.key.Close())
		if e == nil {
			probe, x := registry.OpenKey(s.parent, r.Name, registry.READ)
			if x == nil {
				e = errors.Join(errors.New("registration still present"), probe.Close())
			} else if !errors.Is(x, syscall.ERROR_FILE_NOT_FOUND) {
				e = x
			}
		}
		if e == nil {
			r.Deleted = true
			r.Retained = false
		}
		err = errors.Join(err, e)
	}
	if s.parent != 0 {
		err = errors.Join(err, s.parent.Close())
	}
	return err
}

type hvPolicy struct {
	result              *policyResult
	services, canaryIDs []guid.GUID
	canaries            []*ownedCanary
	session             *policySession
	cleanupErr          error
	control             bool
}

func initialPolicyServices() []guid.GUID {
	ids := []guid.GUID{prot.WindowsGcsHvsockServiceID}
	for p := uint32(prot.LinuxGcsVsockPort + 1); p <= prot.LinuxGcsVsockPort+6; p++ {
		ids = append(ids, winio.VsockServiceID(p))
	}
	return ids
}

func configurePolicy(o *uvm.OptionsWCOW, ids []guid.GUID, control bool) (*hvPolicy, error) {
	if len(ids) != 5 {
		return nil, errors.New("five owned canary IDs required")
	}
	user, e := windows.GetCurrentProcessToken().GetTokenUser()
	if e != nil {
		return nil, e
	}
	n, e := guid.NewV4()
	if e != nil {
		return nil, e
	}
	profile := "restricted"
	if control {
		profile = "control"
	}
	r := &policyResult{Profile: profile, BrokerSID: user.User.Sid.String(), Nonce: strings.ReplaceAll(n.String(), "-", "")}
	if control {
		r.Nonce = "0" + r.Nonce[1:]
	} else {
		r.Nonce = "1" + r.Nonce[1:]
	} // Distinct profile nonces by construction.
	h := &hvPolicy{result: r, services: initialPolicyServices(), canaryIDs: ids, control: control}
	allow := "D:P(A;;FA;;;" + r.BrokerSID + ")"
	for _, id := range ids {
		r.Canaries = append(r.Canaries, id.String())
	}
	for _, id := range h.services {
		o.AdditionalHyperVConfig[id.String()] = hcsschema.HvSocketServiceConfig{BindSecurityDescriptor: allow, ConnectSecurityDescriptor: denyHv}
		r.Allowed = append(r.Allowed, id.String())
	}
	if control {
		for i, id := range ids {
			connect := denyHv
			if i == 4 {
				connect = allow
			}
			o.AdditionalHyperVConfig[id.String()] = hcsschema.HvSocketServiceConfig{BindSecurityDescriptor: allow, ConnectSecurityDescriptor: connect, AllowWildcardBinds: i < 4}
			r.Allowed = append(r.Allowed, id.String())
		}
	}
	return h, nil
}
func (h *hvPolicy) openCanaries(vm *uvm.UtilityVM) error {
	scopes := []guid.GUID{winio.HvsockGUIDWildcard(), winio.HvsockGUIDChildren(), winio.HvsockGUIDWildcard(), winio.HvsockGUIDChildren()}
	for i, scope := range scopes {
		l, e := winio.ListenHvsock(&winio.HvsockAddr{VMID: scope, ServiceID: h.canaryIDs[i]})
		if e != nil {
			return e
		}
		c := &ownedCanary{l: l, nonce: h.result.Nonce, done: make(chan error, 1)}
		h.canaries = append(h.canaries, c)
		go c.serve()
	}
	return nil
}
func (h *hvPolicy) closeHostCanaries() error {
	for _, c := range h.canaries {
		h.cleanupErr = errors.Join(h.cleanupErr, c.close())
		c.mu.Lock()
		h.result.HostAcceptCounts = append(h.result.HostAcceptCounts, c.receipts)
		c.mu.Unlock()
	}
	h.canaries = nil
	return h.cleanupErr
}
func (h *hvPolicy) close() error {
	e := errors.Join(h.closeHostCanaries(), h.session.close())
	h.result.CleanupOK = e == nil
	return e
}
func checkDialMatrix(got []dialObservation, ids []string, positive bool) error {
	if len(got) != 4 || len(ids) != 4 {
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

func (h *hvPolicy) run(ctx context.Context, vm *uvm.UtilityVM, host cow.Container, r *report) (err error) {
	if err = h.openCanaries(vm); err != nil {
		return err
	}
	if h.control {
		duplicate, e := winio.ListenHvsock(&winio.HvsockAddr{VMID: winio.HvsockGUIDWildcard(), ServiceID: h.canaryIDs[0]})
		if e == nil {
			return errors.Join(errors.New("duplicate listener bind allowed"), duplicate.Close())
		}
		if !errors.Is(e, windows.WSAEADDRINUSE) {
			return e
		}
		h.result.ExclusiveBindVerified = true
	}
	h.session, err = startPolicySession(ctx, host)
	if err != nil {
		return err
	}
	peers, e := h.session.exchange(ctx, h.result.Profile, h.result.Nonce, h.result.Canaries)
	h.result.HostDials = peers.Dials
	if e != nil {
		return e
	}
	err = checkDialMatrix(peers.Dials, h.result.Canaries[:4], h.control)
	err = errors.Join(err, h.closeHostCanaries())
	for _, n := range h.result.HostAcceptCounts {
		want := 0
		if h.control {
			want = 1
		}
		if n != want {
			err = errors.Join(err, errors.New("host canary accepted-count mismatch"))
		}
	}
	if err != nil {
		return err
	}
	for _, id := range h.canaryIDs {
		if h.control {
			o := bindObservation{Service: id.String()}
			l, e := winio.ListenHvsock(&winio.HvsockAddr{VMID: vm.RuntimeID(), ServiceID: id})
			if e == nil {
				o.Allowed = true
				e = l.Close()
				o.Closed = e == nil
			}
			if e != nil {
				o.Error = e.Error()
			}
			h.result.Binds = append(h.result.Binds, o)
			err = errors.Join(err, e)
		} else {
			o := denyNewBind(vm.RuntimeID(), id)
			h.result.Binds = append(h.result.Binds, o)
			if !o.Denied {
				err = errors.Join(err, errors.New("restricted exact bind permitted"))
			}
		}
	}
	if err != nil {
		return err
	}
	ready, e := h.session.exchange(ctx, "guest-listen", h.result.Nonce, h.result.Canaries)
	h.result.GuestListener = ready.Listener
	if e != nil {
		return e
	}
	if ready.Listener == nil || !ready.Listener.Ready {
		return errors.New("guest listener readiness absent")
	}
	endpoint, e := queryOwnedContainerEndpoint(ctx, host, r.ID+"-guest", r.ContainerSystemGUID, vm.RuntimeID())
	if e != nil {
		return e
	}
	h.result.HostConnect = policyDial(h.result.Canaries[4], h.result.Nonce, endpoint)
	closed, e := h.session.exchange(ctx, "guest-close", h.result.Nonce, h.result.Canaries)
	h.result.GuestListener = closed.Listener
	if e != nil {
		return e
	}
	if closed.Listener == nil || !closed.Listener.Ready || !closed.Listener.Closed || closed.Listener.Error != "" {
		return errors.New("guest listener closure incomplete")
	}
	o := h.result.HostConnect
	if h.control {
		if !o.Connected || !o.Echo || o.Error != "" || o.CloseError != "" || closed.Listener.Accepted != 1 {
			return errors.New("host connect positive control failed")
		}
	} else if !policyDialDenied(o) || closed.Listener.Accepted != 0 {
		return errors.New("host connect denial not proven")
	}
	for _, id := range h.services {
		l, e := winio.ListenHvsock(&winio.HvsockAddr{VMID: vm.RuntimeID(), ServiceID: id})
		if e != nil {
			return e
		}
		if e = l.Close(); e != nil {
			return e
		}
		h.result.ListenerRelease = append(h.result.ListenerRelease, id.String())
	}
	h.result.MatrixPassed = true
	if !h.control {
		runtimes, e := h.session.exchange(ctx, "runtimes", h.result.Nonce, h.result.Canaries)
		r.Cases = append(r.Cases, runtimes.Cases...)
		if e != nil {
			return e
		}
		if len(runtimes.Cases) != 6 {
			return errors.New("restricted runtime inventory")
		}
		for _, c := range runtimes.Cases {
			if !c.Passed {
				return fmt.Errorf("restricted runtime failed: %s", c.Name)
			}
		}
		r.RuntimePassed = true
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
