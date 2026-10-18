package lobby

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"syscall"
	"testing"
	"time"

	"github.com/pdabel/fs-uae-launcher/fsnp-server/internal/fsnp"
	"github.com/pdabel/fs-uae-launcher/fsnp-server/internal/game"
)

var emuVersion = [8]byte{'F', 'S', 'U', 'A', 'E', 3, 1, 66}

type harness struct {
	t    *testing.T
	l    *Lobby
	addr string
	stop func() error
}

// startLobby serves a lobby on a loopback port. Everything — HTTP, PING and
// FSNP — goes to that one port, as it does in production.
func startLobby(t *testing.T, cfg Config) *harness {
	t.Helper()
	if cfg.Logger == nil {
		cfg.Logger = slog.New(slog.NewTextHandler(io.Discard, nil))
	}
	ln, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	l := New(cfg)
	ctx, cancel := context.WithCancel(context.Background())
	errc := make(chan error, 1)
	go func() { errc <- l.Serve(ctx, ln) }()
	var stopped bool
	var serveErr error
	stop := func() error {
		if !stopped {
			stopped = true
			cancel()
			select {
			case serveErr = <-errc:
			case <-time.After(10 * time.Second):
				t.Fatal("Serve did not return")
			}
		}
		return serveErr
	}
	t.Cleanup(func() { _ = stop() })
	return &harness{t: t, l: l, addr: ln.Addr().String(), stop: stop}
}

// create calls /game/create and returns the status and parsed body.
func (h *harness) create(query string) (int, url.Values) {
	h.t.Helper()
	return h.createWithHost(query, "")
}

func (h *harness) createWithHost(query, host string) (int, url.Values) {
	h.t.Helper()
	req, err := http.NewRequest("GET", "http://"+h.addr+"/game/create?"+query, nil)
	if err != nil {
		h.t.Fatal(err)
	}
	if host != "" {
		req.Host = host
	}
	resp, err := (&http.Client{Timeout: 5 * time.Second}).Do(req)
	if err != nil {
		h.t.Fatal(err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return resp.StatusCode, nil
	}
	v, err := url.ParseQuery(string(body))
	if err != nil {
		h.t.Fatalf("response %q: %v", body, err)
	}
	return resp.StatusCode, v
}

func (h *harness) createOK(players int, password string) url.Values {
	h.t.Helper()
	q := url.Values{"players": {strconv.Itoa(players)}, "password": {password}}
	status, v := h.create(q.Encode())
	if status != http.StatusOK {
		h.t.Fatalf("create: status %d", status)
	}
	return v
}

func (h *harness) waitLen(n int) {
	h.t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for h.l.Len() != n {
		if time.Now().After(deadline) {
			h.t.Fatalf("lobby has %d games, want %d", h.l.Len(), n)
		}
		time.Sleep(5 * time.Millisecond)
	}
}

// client is an emulator's side of one TCP connection to the lobby.
type client struct {
	t  *testing.T
	nc net.Conn
}

func (h *harness) dial() *client {
	h.t.Helper()
	nc, err := net.DialTimeout("tcp4", h.addr, 5*time.Second)
	if err != nil {
		h.t.Fatal(err)
	}
	h.t.Cleanup(func() { _ = nc.Close() })
	return &client{t: h.t, nc: nc}
}

func (h *harness) join(password, tag string) *client {
	h.t.Helper()
	hs := fsnp.Handshake{
		ProtocolVersion: fsnp.ProtocolVersion,
		PasswordHash:    fsnp.ExpectedPasswordHash(password),
		EmulatorVersion: emuVersion,
		Player:          fsnp.NewPlayerByte,
	}
	copy(hs.Tag[:], tag)
	return h.joinWith(hs)
}

func (h *harness) joinWith(hs fsnp.Handshake) *client {
	h.t.Helper()
	c := h.dial()
	b := hs.Encode()
	c.write(b[:])
	return c
}

// joinOK joins and returns the player number from the PLAYERS reply.
func (h *harness) joinOK(password, tag string) (*client, int) {
	h.t.Helper()
	c := h.join(password, tag)
	c.expectExt(fsnp.CmdSessionKey)
	return c, int(c.expectExt(fsnp.CmdPlayers).Data() >> 8)
}

func (c *client) write(b []byte) {
	c.t.Helper()
	_ = c.nc.SetWriteDeadline(time.Now().Add(5 * time.Second))
	if _, err := c.nc.Write(b); err != nil {
		c.t.Fatalf("write: %v", err)
	}
}

// next reads one word, consuming a TEXT payload if it carries one.
func (c *client) next() fsnp.Message {
	c.t.Helper()
	_ = c.nc.SetReadDeadline(time.Now().Add(5 * time.Second))
	var w [4]byte
	if _, err := io.ReadFull(c.nc, w[:]); err != nil {
		c.t.Fatalf("read: %v", err)
	}
	m := fsnp.DecodeMessage(w[:])
	if m.IsExt() && m.Command() == fsnp.CmdText {
		if _, err := io.ReadFull(c.nc, make([]byte, m.Data()&0xFFFF)); err != nil {
			c.t.Fatalf("read text: %v", err)
		}
	}
	return m
}

func (c *client) expectExt(cmd byte) fsnp.Message {
	c.t.Helper()
	m := c.next()
	if !m.IsExt() || m.Command() != cmd {
		c.t.Fatalf("got %08x, want ext command %d", uint32(m), cmd)
	}
	return m
}

// waitFrame reads past tags, status and pings to the next frame word.
func (c *client) waitFrame() uint32 {
	c.t.Helper()
	for {
		if m := c.next(); m.IsFrame() {
			return m.FrameNumber()
		}
	}
}

// waitError reads to the next ERROR word and checks its code.
func (c *client) waitError(code byte) {
	c.t.Helper()
	for {
		m := c.next()
		if m.IsExt() && m.Command() == fsnp.CmdError {
			if m.Data() != uint32(code) {
				c.t.Fatalf("got error %d, want %d", m.Data(), code)
			}
			return
		}
	}
}

// expectClosed waits for the server to close the connection. sendError puts
// the ERROR word ahead of anything already queued, which is still flushed
// behind it, so there may be bytes to discard first; the emulator itself
// disconnects on reading the ERROR word and never sees them.
func (c *client) expectClosed() {
	c.t.Helper()
	_ = c.nc.SetReadDeadline(time.Now().Add(5 * time.Second))
	if _, err := io.Copy(io.Discard, c.nc); err != nil {
		c.t.Fatalf("got err=%v, want EOF", err)
	}
}

func TestCreateAndPlay(t *testing.T) {
	h := startLobby(t, Config{})
	v := h.createOK(2, "secret")

	if v.Get("password") != "secret" {
		t.Fatalf("password %q, want secret", v.Get("password"))
	}
	_, port, _ := net.SplitHostPort(h.addr)
	if v.Get("port") != port {
		t.Fatalf("port %q, want the lobby's own %s", v.Get("port"), port)
	}
	if v.Get("addresses") != "127.0.0.1" {
		t.Fatalf("addresses %q, want 127.0.0.1 from the Host header", v.Get("addresses"))
	}
	if !regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`).MatchString(v.Get("id")) {
		t.Fatalf("id %q is not a UUIDv4", v.Get("id"))
	}

	c1, n1 := h.joinOK("secret", "P1")
	c2, n2 := h.joinOK("secret", "P2")
	if n1 != 0 || n2 != 1 {
		t.Fatalf("joined as %d and %d, want 0 and 1", n1, n2)
	}
	for _, c := range []*client{c1, c2} {
		if f := c.waitFrame(); f != 1 {
			t.Fatalf("first frame %d, want 1", f)
		}
	}
}

// TestTwoGamesOnePort runs two games through the same port at once: each
// player lands in the game its password names, and one game ending leaves
// the other running.
func TestTwoGamesOnePort(t *testing.T) {
	h := startLobby(t, Config{})
	h.createOK(2, "alpha")
	h.createOK(2, "beta")

	a1, _ := h.joinOK("alpha", "A1")
	b1, nb1 := h.joinOK("beta", "B1")
	a2, na2 := h.joinOK("alpha", "A2")
	b2, nb2 := h.joinOK("beta", "B2")
	// Slots are per game, so each game numbers its players from 0.
	if nb1 != 0 || na2 != 1 || nb2 != 1 {
		t.Fatalf("players b1=%d a2=%d b2=%d, want 0 1 1", nb1, na2, nb2)
	}
	for _, c := range []*client{a1, a2, b1, b2} {
		c.waitFrame()
	}

	_ = a1.nc.Close()
	a2.waitError(fsnp.ErrGameStopped)
	a2.expectClosed()
	h.waitLen(1)

	// Game B is unaffected: it keeps ticking. Acks keep it under the drift
	// stall so frames keep coming.
	for _, c := range []*client{b1, b2} {
		f := c.waitFrame()
		c.write(encode(fsnp.NewFrameMessage(f)))
		if g := c.waitFrame(); g <= f {
			t.Fatalf("frame went from %d to %d", f, g)
		}
	}

	// A's password is free again.
	h.createOK(2, "alpha")
}

func encode(m fsnp.Message) []byte {
	w := m.Encode()
	return w[:]
}

func TestPingAndHTTPShareThePort(t *testing.T) {
	h := startLobby(t, Config{})

	c := h.dial()
	c.write([]byte("PING"))
	reply := make([]byte, 4)
	_ = c.nc.SetReadDeadline(time.Now().Add(5 * time.Second))
	if _, err := io.ReadFull(c.nc, reply); err != nil || string(reply) != "PONG" {
		t.Fatalf("got %q err=%v, want PONG", reply, err)
	}
	c.expectClosed()

	resp, err := http.Get("http://" + h.addr + "/healthz")
	if err != nil {
		t.Fatal(err)
	}
	body, _ := io.ReadAll(resp.Body)
	resp.Body.Close()
	if resp.StatusCode != 200 || strings.TrimSpace(string(body)) != "ok" {
		t.Fatalf("healthz: %d %q", resp.StatusCode, body)
	}

	resp, err = http.Get("http://" + h.addr + "/nope")
	if err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusNotFound {
		t.Fatalf("unknown path: %d, want 404", resp.StatusCode)
	}
}

func TestUnknownPasswordRejected(t *testing.T) {
	h := startLobby(t, Config{})
	h.createOK(2, "secret")

	for _, password := range []string{"wrong", ""} {
		c := h.join(password, "P1")
		c.waitError(fsnp.ErrWrongPassword)
		c.expectClosed()
	}
}

func TestProtocolMismatch(t *testing.T) {
	h := startLobby(t, Config{})
	h.createOK(2, "secret")
	hs := fsnp.Handshake{
		ProtocolVersion: fsnp.ProtocolVersion + 1,
		PasswordHash:    fsnp.PasswordHash("secret"),
		EmulatorVersion: emuVersion,
		Player:          fsnp.NewPlayerByte,
	}
	c := h.joinWith(hs)
	c.waitError(fsnp.ErrProtocolMismatch)
	c.expectClosed()
}

func TestCreateRejections(t *testing.T) {
	h := startLobby(t, Config{MaxGames: 2})
	h.createOK(2, "secret")

	cases := []struct {
		query string
		want  int
	}{
		{"players=2&password=secret", http.StatusConflict},
		{"players=0&password=x", http.StatusBadRequest},
		{"players=7&password=x", http.StatusBadRequest},
		{"players=two&password=x", http.StatusBadRequest},
		{"password=x", http.StatusBadRequest},
		{"players=2&password=" + strings.Repeat("x", MaxPasswordLength+1), http.StatusBadRequest},
	}
	for _, tc := range cases {
		if status, _ := h.create(tc.query); status != tc.want {
			t.Errorf("%s: status %d, want %d", tc.query, status, tc.want)
		}
	}
	if h.l.Len() != 1 {
		t.Fatalf("rejected creates left %d games, want 1", h.l.Len())
	}

	h.createOK(2, "other")
	if status, _ := h.create("players=2&password=third"); status != http.StatusServiceUnavailable {
		t.Fatalf("past MaxGames: status %d, want 503", status)
	}
}

func TestGeneratedPassword(t *testing.T) {
	h := startLobby(t, Config{})
	a := h.createOK(2, "")
	b := h.createOK(2, "")
	pa, pb := a.Get("password"), b.Get("password")
	if len(pa) != generatedPasswordLength || len(pb) != generatedPasswordLength {
		t.Fatalf("generated %q and %q, want %d characters", pa, pb, generatedPasswordLength)
	}
	if pa == pb {
		t.Fatalf("both games got password %q", pa)
	}
	for _, r := range pa + pb {
		if !strings.ContainsRune(passwordAlphabet, r) {
			t.Fatalf("generated password has %q, outside the alphabet", r)
		}
	}
	if _, n := h.joinOK(pa, "P1"); n != 0 {
		t.Fatalf("joined as %d, want 0", n)
	}
}

func TestAddresses(t *testing.T) {
	h := startLobby(t, Config{})
	_, v := h.createWithHost("players=2&password=a", "lobby.example:30000")
	if v.Get("addresses") != "lobby.example" || v.Get("port") != "30000" {
		t.Fatalf("got addresses=%q port=%q, want lobby.example and the Host header's port",
			v.Get("addresses"), v.Get("port"))
	}
	// No port in Host: the client used HTTP's default port, so a mapping
	// such as 80 -> 25101 must report 80, not the container's 25101.
	_, v = h.createWithHost("players=2&password=b", "lobby.example")
	if v.Get("port") != "80" {
		t.Fatalf("Host without a port: got port=%q, want 80", v.Get("port"))
	}

	p := startLobby(t, Config{PublicAddresses: []string{"203.0.113.4", "lan.example"}})
	_, v = p.create("players=2&password=c")
	if v.Get("addresses") != "203.0.113.4,lan.example" {
		t.Fatalf("got addresses=%q, want the configured list", v.Get("addresses"))
	}
}

// stillClock is a game.Clock that never ticks and fires the launch timeout
// only when told to.
type stillClock struct{ after chan time.Time }

func (c stillClock) Now() time.Time                       { return time.Now() }
func (c stillClock) NewTicker(time.Duration) game.Ticker  { return stillTicker{} }
func (c stillClock) After(time.Duration) <-chan time.Time { return c.after }

type stillTicker struct{}

func (stillTicker) C() <-chan time.Time { return nil }
func (stillTicker) Stop()               {}

func TestLaunchTimeoutReaps(t *testing.T) {
	clock := stillClock{after: make(chan time.Time)}
	h := startLobby(t, Config{Clock: clock})
	h.createOK(2, "secret")
	c, _ := h.joinOK("secret", "P1")

	close(clock.after)
	c.waitError(fsnp.ErrGameStopped)
	h.waitLen(0)
	h.createOK(2, "secret")
}

func TestShutdownStopsGames(t *testing.T) {
	h := startLobby(t, Config{})
	h.createOK(2, "alpha")
	h.createOK(2, "beta")
	a, _ := h.joinOK("alpha", "A1")
	b, _ := h.joinOK("beta", "B1")

	if err := h.stop(); err != nil {
		t.Fatalf("Serve returned %v", err)
	}
	for _, c := range []*client{a, b} {
		c.waitError(fsnp.ErrGameStopped)
		c.expectClosed()
	}
	if h.l.Len() != 0 {
		t.Fatalf("%d games left after shutdown", h.l.Len())
	}
	if _, err := h.l.Create(2, "gamma"); !errors.Is(err, ErrClosed) {
		t.Fatalf("Create after shutdown: %v, want ErrClosed", err)
	}
	if _, err := net.DialTimeout("tcp4", h.addr, time.Second); err == nil {
		t.Fatal("lobby port still accepting after shutdown")
	}
}

// TestResponseParsesInLauncher pins the body format to what /startgame's
// parse_qs reads: four keys, form-encoded, a password with reserved
// characters surviving the round trip.
func TestResponseParsesInLauncher(t *testing.T) {
	h := startLobby(t, Config{})
	v := h.createOK(2, "a&b=c d#")
	for _, k := range []string{"id", "password", "port", "addresses"} {
		if len(v[k]) != 1 {
			t.Fatalf("key %q: %v", k, v[k])
		}
	}
	if v.Get("password") != "a&b=c d#" {
		t.Fatalf("password %q", v.Get("password"))
	}
}

// TestHTTPConnectionsAreBounded: an HTTP client can't hold a connection open
// indefinitely, either idle after a response or by promising a body it
// never sends. Held connections would otherwise pile up until the process
// runs out of file descriptors.
func TestHTTPConnectionsAreBounded(t *testing.T) {
	defer func(r, i time.Duration) { httpReadTimeout, httpIdleTimeout = r, i }(httpReadTimeout, httpIdleTimeout)
	httpReadTimeout, httpIdleTimeout = 200*time.Millisecond, 200*time.Millisecond
	h := startLobby(t, Config{})

	for _, tc := range []struct{ name, req string }{
		{"idle after response", "GET /healthz HTTP/1.1\r\nHost: x\r\n\r\n"},
		{"body never sent", "GET /healthz HTTP/1.1\r\nHost: x\r\nContent-Length: 1\r\n\r\n"},
	} {
		c := h.dial()
		c.write([]byte(tc.req))
		_ = c.nc.SetReadDeadline(time.Now().Add(5 * time.Second))
		if _, err := io.Copy(io.Discard, c.nc); err != nil {
			t.Fatalf("%s: connection not closed by the server: %v", tc.name, err)
		}
	}
}

// flakyListener fails its first n Accepts with a non-timeout error, as a
// process out of file descriptors does.
type flakyListener struct {
	net.Listener
	n int
}

func (l *flakyListener) Accept() (net.Conn, error) {
	if l.n > 0 {
		l.n--
		return nil, &net.OpError{Op: "accept", Net: "tcp", Err: syscall.EMFILE}
	}
	return l.Listener.Accept()
}

// TestAcceptErrorsDoNotStopTheLobby: a failing Accept is retried, not
// returned, because returning would stop every game in the lobby.
func TestAcceptErrorsDoNotStopTheLobby(t *testing.T) {
	ln, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	l := New(Config{Logger: slog.New(slog.NewTextHandler(io.Discard, nil))})
	ctx, cancel := context.WithCancel(context.Background())
	errc := make(chan error, 1)
	go func() { errc <- l.Serve(ctx, &flakyListener{Listener: ln, n: 5}) }()
	h := &harness{t: t, l: l, addr: ln.Addr().String()}
	defer func() {
		cancel()
		<-errc
	}()

	h.createOK(2, "secret")
	if _, n := h.joinOK("secret", "P1"); n != 0 {
		t.Fatalf("joined as %d, want 0", n)
	}
	select {
	case err := <-errc:
		t.Fatalf("Serve returned %v after accept errors", err)
	default:
	}
}

func TestHostAndPort(t *testing.T) {
	local := &net.TCPAddr{IP: net.IPv4(127, 0, 0, 1), Port: 25101}
	for _, tc := range []struct{ hostHeader, host, port string }{
		{"lobby.example:30000", "lobby.example", "30000"},
		{"lobby.example", "lobby.example", "80"},
		{"[2001:db8::1]:25101", "2001:db8::1", "25101"},
		{"[2001:db8::1]", "2001:db8::1", "80"},
		{"", "", "25101"}, // no Host at all: only the listener is left
	} {
		r := httptest.NewRequest("GET", "/game/create", nil)
		r.Host = tc.hostHeader
		r = r.WithContext(context.WithValue(r.Context(), http.LocalAddrContextKey, net.Addr(local)))
		if host, port := hostAndPort(r); host != tc.host || port != tc.port {
			t.Errorf("Host %q: got %q %q, want %q %q", tc.hostHeader, host, port, tc.host, tc.port)
		}
	}
}
