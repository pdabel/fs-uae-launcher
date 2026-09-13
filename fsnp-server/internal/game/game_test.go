package game

import (
	"bytes"
	"context"
	"errors"
	"io"
	"log/slog"
	"net"
	"os"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/pdabel/fs-uae-launcher/fsnp-server/internal/fsnp"
)

const testPassword = "secret"

var emuVersion = [8]byte{'F', 'S', 'U', 'A', 'E', 3, 1, 66}

// fakeClock is driven entirely by the test: Tick delivers one ticker tick
// (and advances Now by FrameInterval), FireLaunchTimeout fires After.
type fakeClock struct {
	mu    sync.Mutex
	now   time.Time
	ticks chan time.Time
	after chan time.Time
}

func newFakeClock() *fakeClock {
	return &fakeClock{
		now:   time.Unix(1_700_000_000, 0),
		ticks: make(chan time.Time),
		after: make(chan time.Time, 1),
	}
}

func (f *fakeClock) Now() time.Time {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.now
}

func (f *fakeClock) Advance(d time.Duration) {
	f.mu.Lock()
	f.now = f.now.Add(d)
	f.mu.Unlock()
}

func (f *fakeClock) NewTicker(time.Duration) Ticker       { return fakeTicker{f.ticks} }
func (f *fakeClock) After(time.Duration) <-chan time.Time { return f.after }

// Tick advances the clock one frame and blocks until the game goroutine has
// taken the tick.
func (f *fakeClock) Tick(t *testing.T) {
	t.Helper()
	f.Advance(FrameInterval)
	select {
	case f.ticks <- f.Now():
	case <-time.After(5 * time.Second):
		t.Fatal("game did not consume tick")
	}
}

type fakeTicker struct{ c chan time.Time }

func (f fakeTicker) C() <-chan time.Time { return f.c }
func (fakeTicker) Stop()                 {}

// harness is one running game plus the test's handle on it.
type harness struct {
	t      *testing.T
	g      *Game
	clock  *fakeClock
	cancel context.CancelFunc
	runErr chan error
}

func newHarness(t *testing.T, players int, launchTimeout time.Duration) *harness {
	t.Helper()
	clock := newFakeClock()
	g, err := New(Config{
		Players:       players,
		PasswordHash:  fsnp.PasswordHash(testPassword),
		LaunchTimeout: launchTimeout,
		Clock:         clock,
		Logger:        slog.New(slog.NewTextHandler(io.Discard, nil)),
	})
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	h := &harness{t: t, g: g, clock: clock, cancel: cancel, runErr: make(chan error, 1)}
	go func() { h.runErr <- g.Run(ctx) }()
	t.Cleanup(func() {
		cancel()
		select {
		case <-g.Done():
		case <-time.After(5 * time.Second):
			t.Error("game did not stop on cleanup")
		}
	})
	return h
}

// tick delivers one tick and waits for the game goroutine to finish
// handling it (Stats is answered by the same goroutine, in order).
func (h *harness) tick() {
	h.clock.Tick(h.t)
	h.g.Stats()
}

func (h *harness) waitRun() error {
	h.t.Helper()
	select {
	case err := <-h.runErr:
		return err
	case <-time.After(5 * time.Second):
		h.t.Fatal("Run did not return")
		return nil
	}
}

// waitFrames polls until every player has acked frame want.
func (h *harness) waitFrames(want uint32) {
	h.t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		s := h.g.Stats()
		ok := len(s.Players) > 0
		for _, p := range s.Players {
			if p.Frame != want {
				ok = false
			}
		}
		if ok {
			return
		}
		time.Sleep(50 * time.Microsecond)
	}
	h.t.Fatalf("players never reached frame %d: %+v", want, h.g.Stats())
}

// waitPlayerFrame polls until player slot has acked frame want.
func (h *harness) waitPlayerFrame(slot int, want uint32) {
	h.t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		for _, p := range h.g.Stats().Players {
			if p.Slot == slot && p.Frame == want {
				return
			}
		}
		time.Sleep(50 * time.Microsecond)
	}
	h.t.Fatalf("player %d never reached frame %d: %+v", slot, want, h.g.Stats())
}

// waitPing polls until player slot's averaged ping equals want.
func (h *harness) waitPing(slot int, want time.Duration) {
	h.t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		for _, p := range h.g.Stats().Players {
			if p.Slot == slot && p.PingAvg == want {
				return
			}
		}
		time.Sleep(50 * time.Microsecond)
	}
	h.t.Fatalf("player %d ping never reached %v: %+v", slot, want, h.g.Stats())
}

type textMsg struct {
	from int
	text string
}

// client is the test's side of one net.Pipe, with a goroutine decoding
// everything the server sends.
type client struct {
	t      *testing.T
	nc     net.Conn
	words  chan fsnp.Message
	texts  chan textMsg
	closed chan struct{}
}

func handshake(tag string) fsnp.Handshake {
	hs := fsnp.Handshake{
		ProtocolVersion:  fsnp.ProtocolVersion,
		PasswordHash:     fsnp.PasswordHash(testPassword),
		EmulatorVersion:  emuVersion,
		Player:           fsnp.NewPlayerByte,
		ResumeFromPacket: 0,
	}
	copy(hs.Tag[:], tag)
	return hs
}

// dial connects a raw pipe to the game without sending anything.
func (h *harness) dial() *client {
	server, clientSide := net.Pipe()
	go h.g.HandleConn(server)
	c := &client{
		t:      h.t,
		nc:     clientSide,
		words:  make(chan fsnp.Message, 200000),
		texts:  make(chan textMsg, 64),
		closed: make(chan struct{}),
	}
	go c.readLoop()
	return c
}

// join connects and sends the given handshake.
func (h *harness) join(hs fsnp.Handshake) *client {
	h.t.Helper()
	c := h.dial()
	b := hs.Encode()
	c.write(b[:])
	return c
}

// joinOK connects with a default handshake and consumes the SESSION_KEY and
// PLAYERS response, returning the assigned player number.
func (h *harness) joinOK(tag string) (*client, int) {
	h.t.Helper()
	c := h.join(handshake(tag))
	c.expectExt(fsnp.CmdSessionKey)
	players := c.expectExt(fsnp.CmdPlayers)
	return c, int(players.Data() >> 8)
}

func (c *client) readLoop() {
	defer close(c.closed)
	var word [4]byte
	for {
		if _, err := io.ReadFull(c.nc, word[:]); err != nil {
			return
		}
		m := fsnp.DecodeMessage(word[:])
		if m.IsExt() && m.Command() == fsnp.CmdText {
			n := m.Data() & 0xFFFF
			buf := make([]byte, n)
			if _, err := io.ReadFull(c.nc, buf); err != nil {
				return
			}
			c.texts <- textMsg{from: int(m.Data() >> 16), text: string(buf)}
			continue
		}
		c.words <- m
	}
}

func (c *client) write(b []byte) {
	c.t.Helper()
	done := make(chan error, 1)
	go func() {
		_, err := c.nc.Write(b)
		done <- err
	}()
	select {
	case err := <-done:
		if err != nil {
			c.t.Fatalf("write: %v", err)
		}
	case <-time.After(5 * time.Second):
		c.t.Fatal("write blocked")
	}
}

func (c *client) send(ms ...fsnp.Message) {
	c.t.Helper()
	var b []byte
	for _, m := range ms {
		w := m.Encode()
		b = append(b, w[:]...)
	}
	c.write(b)
}

// ackFrame sends what the emulator sends per frame: RND_CHECK, MEM_CHECK,
// then the frame ack.
func (c *client) ackFrame(frame uint32, rnd, mem uint32) {
	c.t.Helper()
	c.send(
		fsnp.NewExtMessage(fsnp.CmdRndCheck, rnd),
		fsnp.NewExtMessage(fsnp.CmdMemCheck, mem),
		fsnp.NewFrameMessage(frame),
	)
}

func (c *client) next() fsnp.Message {
	c.t.Helper()
	select {
	case m := <-c.words:
		return m
	case <-time.After(5 * time.Second):
		c.t.Fatal("timed out waiting for a word")
		return 0
	}
}

func (c *client) expectExt(cmd byte) fsnp.Message {
	c.t.Helper()
	m := c.next()
	if !m.IsExt() || m.Command() != cmd {
		c.t.Fatalf("got %08x, want ext command %d", uint32(m), cmd)
	}
	return m
}

func (c *client) expectFrame(frame uint32) {
	c.t.Helper()
	m := c.next()
	if !m.IsFrame() || m.FrameNumber() != frame {
		c.t.Fatalf("got %08x, want frame %d", uint32(m), frame)
	}
}

func (c *client) expectError(code byte) {
	c.t.Helper()
	m := c.expectExt(fsnp.CmdError)
	if m.Data() != uint32(code) {
		c.t.Fatalf("got error %d, want %d", m.Data(), code)
	}
}

func (c *client) expectText(from int, text string) {
	c.t.Helper()
	select {
	case m := <-c.texts:
		if m.from != from || m.text != text {
			c.t.Fatalf("got text %+v, want from=%d %q", m, from, text)
		}
	case <-time.After(5 * time.Second):
		c.t.Fatal("timed out waiting for text")
	}
}

func (c *client) expectClosed() {
	c.t.Helper()
	c.expectClosedWithin(5 * time.Second)
}

func (c *client) expectClosedWithin(d time.Duration) {
	c.t.Helper()
	select {
	case <-c.closed:
	case <-time.After(d):
		c.t.Fatal("connection was not closed")
	}
}

func (c *client) expectNothing() {
	c.t.Helper()
	select {
	case m := <-c.words:
		c.t.Fatalf("unexpected word %08x", uint32(m))
	case <-time.After(20 * time.Millisecond):
	}
}

// startTwo joins two players and consumes everything up to and including
// the first frame word for each.
func startTwo(t *testing.T) (*harness, *client, *client) {
	t.Helper()
	h := newHarness(t, 2, 0)
	c1, _ := h.joinOK("P1")
	c1.expectExt(fsnp.CmdPlayerTag0)
	c2, _ := h.joinOK("P2")
	c2.expectExt(fsnp.CmdPlayerTag0)
	c2.expectExt(fsnp.CmdPlayerTag1)
	h.tick()
	for _, c := range []*client{c1, c2} {
		c.expectExt(fsnp.CmdPlayerTag0)
		c.expectExt(fsnp.CmdPlayerTag1)
		for range 2 {
			c.expectExt(fsnp.CmdPlayerLag)
			c.expectExt(fsnp.CmdPlayerPing)
		}
		c.expectFrame(1)
	}
	return h, c1, c2
}

func TestPingProbe(t *testing.T) {
	h := newHarness(t, 2, 0)
	server, clientSide := net.Pipe()
	go h.g.HandleConn(server)
	if _, err := clientSide.Write([]byte("PING")); err != nil {
		t.Fatal(err)
	}
	var reply [4]byte
	if _, err := io.ReadFull(clientSide, reply[:]); err != nil {
		t.Fatal(err)
	}
	if string(reply[:]) != "PONG" {
		t.Fatalf("got %q, want PONG", reply)
	}
	if _, err := clientSide.Read(reply[:]); err != io.EOF {
		t.Fatalf("after PONG got err=%v, want EOF", err)
	}
}

func TestHandshakeRejections(t *testing.T) {
	cases := []struct {
		name string
		mod  func(*fsnp.Handshake)
		code byte
	}{
		{"protocol version", func(h *fsnp.Handshake) { h.ProtocolVersion = 2 }, fsnp.ErrProtocolMismatch},
		{"password", func(h *fsnp.Handshake) { h.PasswordHash++ }, fsnp.ErrWrongPassword},
		{"resume on new player", func(h *fsnp.Handshake) { h.ResumeFromPacket = 7 }, fsnp.ErrClientError},
		{"emulator version", func(h *fsnp.Handshake) { h.EmulatorVersion[7] = 67 }, fsnp.ErrEmulatorMismatch},
		{"rejoin unknown slot", func(h *fsnp.Handshake) { h.Player = 3 }, fsnp.ErrPlayerNumber},
		{"rejoin bad session key", func(h *fsnp.Handshake) { h.Player = 0; h.SessionKey = 1 }, fsnp.ErrSessionKey},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			h := newHarness(t, 3, 0)
			c0 := h.join(handshake("P0"))
			key := c0.expectExt(fsnp.CmdSessionKey).Data()
			c0.expectExt(fsnp.CmdPlayers)
			c0.expectExt(fsnp.CmdPlayerTag0)

			hs := handshake("BAD")
			tc.mod(&hs)
			if tc.name == "rejoin bad session key" && hs.SessionKey == key {
				hs.SessionKey++
			}
			c := h.join(hs)
			c.expectError(tc.code)
			c.expectClosed()
		})
	}

	t.Run("rejoin with valid key cannot resume yet", func(t *testing.T) {
		h := newHarness(t, 2, 0)
		c0 := h.join(handshake("P0"))
		key := c0.expectExt(fsnp.CmdSessionKey).Data()
		hs := handshake("P0")
		hs.Player = 0
		hs.SessionKey = key
		c := h.join(hs)
		c.expectError(fsnp.ErrCannotResume)
		c.expectClosed()
	})

	t.Run("join after start", func(t *testing.T) {
		h, _, _ := startTwo(t)
		c := h.join(handshake("P3"))
		c.expectError(fsnp.ErrGameAlreadyStarted)
		c.expectClosed()
	})
}

func TestHandshakeTimeout(t *testing.T) {
	// The handshake deadline is real time; keep the test fast by only
	// checking the deadline is armed (a Read that would otherwise block
	// forever returns once the socket is closed after the timeout).
	if testing.Short() {
		t.Skip("waits for the 5 s handshake timeout")
	}
	h := newHarness(t, 2, 0)
	c := h.dial()
	c.write([]byte("FS"))
	start := time.Now()
	c.expectClosedWithin(HandshakeTimeout + 5*time.Second)
	if d := time.Since(start); d < HandshakeTimeout/2 {
		t.Fatalf("closed after %v, want about %v", d, HandshakeTimeout)
	}
}

// TestStartupMatchesCapture replays two joins with the captured session's
// tags and checks the server's first words to each client — up to and
// including frame 1 — against internal/fsnp/testdata, word for word except
// the random SESSION_KEY.
func TestStartupMatchesCapture(t *testing.T) {
	h := newHarness(t, 2, 0)
	c1 := h.join(handshake("P1"))
	c1.expectExt(fsnp.CmdSessionKey) // random; compared below by command only
	c2 := h.join(handshake("P2"))
	// c1's PLAYERS/TAG words are already queued; c2's join must land after
	// c1's so player numbers match the capture.
	c2.expectExt(fsnp.CmdSessionKey)
	h.tick()

	for i, c := range []*client{c1, c2} {
		raw, err := os.ReadFile(filepath.Join("..", "fsnp", "testdata", []string{"server-to-client1.bin", "server-to-client2.bin"}[i]))
		if err != nil {
			t.Fatal(err)
		}
		want := fsnp.DecodeMessages(raw)
		// Everything after the first frame word except the session key.
		var got []fsnp.Message
		for {
			m := c.next()
			got = append(got, m)
			if m.IsFrame() {
				break
			}
		}
		want = want[1 : len(got)+1] // drop the SESSION_KEY the test already consumed
		if len(want) != len(got) {
			t.Fatalf("client %d: got %d words, want %d", i+1, len(got), len(want))
		}
		for j := range got {
			if got[j] != want[j] {
				t.Errorf("client %d word %d: got %08x, want %08x", i+1, j+1, uint32(got[j]), uint32(want[j]))
			}
		}
		if !got[len(got)-1].IsFrame() || got[len(got)-1].FrameNumber() != 1 {
			t.Errorf("client %d: stream did not end at frame 1", i+1)
		}
	}
}

func TestInputEchoedToAllOnTick(t *testing.T) {
	h, c1, c2 := startTwo(t)
	c1.send(fsnp.NewInputMessage(0x0101b8))
	c1.expectNothing() // queued until the tick flushes
	h.tick()
	for _, c := range []*client{c1, c2} {
		m := c.next()
		if !m.IsInput() || m.InputEvent() != 0x0101b8 {
			t.Fatalf("got %08x, want input 0101b8", uint32(m))
		}
		c.expectFrame(2)
	}
}

func TestInputBeforeStartIsDropped(t *testing.T) {
	h := newHarness(t, 2, 0)
	c1, _ := h.joinOK("P1")
	c1.expectExt(fsnp.CmdPlayerTag0)
	c1.send(fsnp.NewInputMessage(1))
	h.g.Stats()
	c1.expectNothing()
}

func TestAutoFlushAt100Entries(t *testing.T) {
	h, c1, c2 := startTwo(t)
	for i := range 99 {
		c1.send(fsnp.NewInputMessage(uint32(i)))
	}
	h.g.Stats()
	c2.expectNothing()
	c1.send(fsnp.NewInputMessage(99))
	for _, c := range []*client{c1, c2} {
		for i := range 100 {
			m := c.next()
			if !m.IsInput() || m.InputEvent() != uint32(i) {
				t.Fatalf("got %08x, want input %d", uint32(m), i)
			}
		}
	}
}

func TestTextBroadcast(t *testing.T) {
	h, c1, c2 := startTwo(t)
	text := []byte("hello")
	w := fsnp.NewExtMessage(fsnp.CmdText, uint32(len(text))).Encode()
	c2.write(append(w[:], text...))
	h.tick()
	c1.expectText(1, "hello")
	c2.expectText(1, "hello")
}

func TestOversizedTextDropsPlayer(t *testing.T) {
	h, c1, c2 := startTwo(t)
	c2.send(fsnp.NewExtMessage(fsnp.CmdText, MaxTextLength+1))
	c2.expectClosed()
	c1.expectText(1, "P2 disconnected")
	c1.expectError(fsnp.ErrGameStopped)
	if err := h.waitRun(); err != nil {
		t.Fatalf("Run = %v, want nil", err)
	}
}

func TestSyncCheckVerifiesEveryFrame(t *testing.T) {
	h, c1, c2 := startTwo(t)
	for f := uint32(1); f <= 5; f++ {
		if f > 1 {
			h.tick()
			c1.expectFrame(f)
			c2.expectFrame(f)
		}
		c1.ackFrame(f, 0x100+f, 0x200+f)
		c2.ackFrame(f, 0x100+f, 0x200+f)
		h.waitFrames(f)
	}
	h.tick()
	s := h.g.Stats()
	// Tag k is verified once both players acked k+1; both acked 5.
	if s.Verified != 4 {
		t.Fatalf("verified = %d, want 4", s.Verified)
	}
	if s.Frame != 6 {
		t.Fatalf("frame = %d, want 6", s.Frame)
	}
}

func TestDesyncStopsGame(t *testing.T) {
	cases := []struct {
		name string
		rnd  [2]uint32
		mem  [2]uint32
		code byte
	}{
		{"mem", [2]uint32{1, 1}, [2]uint32{2, 3}, fsnp.ErrMemoryDesync},
		{"rnd", [2]uint32{1, 2}, [2]uint32{3, 3}, fsnp.ErrRandomDesync},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			h, c1, c2 := startTwo(t)
			c1.ackFrame(1, tc.rnd[0], tc.mem[0])
			c2.ackFrame(1, tc.rnd[1], tc.mem[1])
			h.waitFrames(1)
			h.clock.Tick(t)
			c1.expectFrame(2)
			c2.expectFrame(2)
			c1.expectError(tc.code)
			c2.expectError(tc.code)
			if err := h.waitRun(); !errors.Is(err, ErrDesync) {
				t.Fatalf("Run = %v, want ErrDesync", err)
			}
			c1.expectClosed()
			c2.expectClosed()
		})
	}
}

func TestDriftStall(t *testing.T) {
	h, c1, c2 := startTwo(t)
	// c1 keeps up; c2 never acks.
	c1.ackFrame(1, 0, 0)
	h.waitPlayerFrame(0, 1)
	var frame uint32 = 1
	for range DefaultMaxDrift + 5 {
		h.tick()
		s := h.g.Stats()
		if s.Frame > frame {
			frame = s.Frame
			c1.expectFrame(frame)
			if frame == 10 {
				c1.expectExt(fsnp.CmdPing) // unanswered, so sent only once
			}
			c1.ackFrame(frame, 0, 0)
			h.waitPlayerFrame(0, frame)
		}
	}
	s := h.g.Stats()
	if !s.Stalled {
		t.Fatalf("expected a stall, stats %+v", s)
	}
	if s.Frame != DefaultMaxDrift+1 {
		t.Fatalf("frame = %d, want %d (stalls once diff exceeds maxDrift)", s.Frame, DefaultMaxDrift+1)
	}
	c1.expectNothing()

	// c2 catches up; the next tick resumes.
	c2.ackFrame(1, 0, 0)
	for f := uint32(2); f <= s.Frame; f++ {
		c2.expectFrame(f)
		if f == 10 {
			c2.expectExt(fsnp.CmdPing)
		}
		c2.ackFrame(f, 0, 0)
	}
	h.waitFrames(s.Frame)
	h.tick()
	s2 := h.g.Stats()
	if s2.Stalled || s2.Frame != s.Frame+1 {
		t.Fatalf("after catch-up stats = %+v, want frame %d unstalled", s2, s.Frame+1)
	}
	c1.expectFrame(s.Frame + 1)
	c2.expectFrame(s.Frame + 1)
}

func TestPlayerLossStopsGameForOthers(t *testing.T) {
	h, c1, c2 := startTwo(t)
	_ = c2.nc.Close()
	c1.expectText(1, "P2 disconnected")
	c1.expectError(fsnp.ErrGameStopped)
	c1.expectClosed()
	if err := h.waitRun(); err != nil {
		t.Fatalf("Run = %v, want nil", err)
	}
}

func TestLeaveBeforeStartFreesSlot(t *testing.T) {
	h := newHarness(t, 2, 0)
	c0, n := h.joinOK("OLD")
	if n != 0 {
		t.Fatalf("first joiner got player %d", n)
	}
	c0.expectExt(fsnp.CmdPlayerTag0)
	_ = c0.nc.Close()
	deadline := time.Now().Add(5 * time.Second)
	for len(h.g.Stats().Players) != 0 {
		if time.Now().After(deadline) {
			t.Fatal("slot was not freed")
		}
		time.Sleep(time.Millisecond)
	}

	c1, n := h.joinOK("NEW")
	if n != 0 {
		t.Fatalf("joiner after a leave got player %d, want 0", n)
	}
	if got := c1.expectExt(fsnp.CmdPlayerTag0).Data(); got != 'N'<<16|'E'<<8|'W' {
		t.Fatalf("tag 0 = %06x, want NEW", got)
	}
	c2, n := h.joinOK("P2")
	if n != 1 {
		t.Fatalf("second joiner got player %d, want 1", n)
	}
	c2.expectExt(fsnp.CmdPlayerTag0)
	c2.expectExt(fsnp.CmdPlayerTag1)
	if !h.g.Stats().Started {
		t.Fatal("game did not start once both slots were filled")
	}
}

func TestCancelSendsGameStopped(t *testing.T) {
	h, c1, c2 := startTwo(t)
	h.cancel()
	c1.expectError(fsnp.ErrGameStopped)
	c2.expectError(fsnp.ErrGameStopped)
	c1.expectClosed()
	c2.expectClosed()
	if err := h.waitRun(); err != nil {
		t.Fatalf("Run = %v, want nil", err)
	}
}

func TestLaunchTimeout(t *testing.T) {
	h := newHarness(t, 2, time.Minute)
	c1, _ := h.joinOK("P1")
	c1.expectExt(fsnp.CmdPlayerTag0)
	h.clock.after <- h.clock.Now()
	c1.expectError(fsnp.ErrGameStopped)
	c1.expectClosed()
	if err := h.waitRun(); !errors.Is(err, ErrLaunchTimeout) {
		t.Fatalf("Run = %v, want ErrLaunchTimeout", err)
	}
}

func TestLaunchTimeoutIgnoredOnceStarted(t *testing.T) {
	h := newHarness(t, 2, time.Minute)
	c1, _ := h.joinOK("P1")
	c1.expectExt(fsnp.CmdPlayerTag0)
	c2, _ := h.joinOK("P2")
	c2.expectExt(fsnp.CmdPlayerTag0)
	c2.expectExt(fsnp.CmdPlayerTag1)
	h.clock.after <- h.clock.Now()
	h.tick()
	c1.expectExt(fsnp.CmdPlayerTag0)
	c1.expectExt(fsnp.CmdPlayerTag1)
	for range 2 {
		c1.expectExt(fsnp.CmdPlayerLag)
		c1.expectExt(fsnp.CmdPlayerPing)
	}
	c1.expectFrame(1)
	select {
	case err := <-h.runErr:
		t.Fatalf("Run returned %v after the game started", err)
	default:
	}
}

func TestPingEvery10FramesAndStatusEvery100(t *testing.T) {
	h, c1, c2 := startTwo(t)
	const rtt = 7 * time.Millisecond
	for f := uint32(2); f <= 101; f++ {
		h.tick()
		if f == 101 {
			// Frame 100 is complete, so the status broadcast precedes 101.
			for _, c := range []*client{c1, c2} {
				for slot := range 2 {
					lag := c.expectExt(fsnp.CmdPlayerLag)
					ping := c.expectExt(fsnp.CmdPlayerPing)
					if int(lag.Data()>>16) != slot || int(ping.Data()>>16) != slot {
						t.Fatalf("status words for wrong slot: %08x %08x", uint32(lag), uint32(ping))
					}
					if slot == 0 && ping.Data()&0xFFFF != uint32(rtt.Milliseconds()) {
						t.Fatalf("player 0 ping = %d ms, want %d", ping.Data()&0xFFFF, rtt.Milliseconds())
					}
					if slot == 1 && ping.Data()&0xFFFF != 0 {
						t.Fatalf("player 1 never answered pings, got %d ms", ping.Data()&0xFFFF)
					}
				}
			}
		}
		c1.expectFrame(f)
		c2.expectFrame(f)
		c1.ackFrame(f, 0, 0)
		c2.ackFrame(f, 0, 0)
		h.waitFrames(f)
		if f%10 == 0 {
			c1.expectExt(fsnp.CmdPing)
			if f == 10 {
				// c2 never answers, so its first PING stays outstanding
				// and no further ones are sent to it.
				c2.expectExt(fsnp.CmdPing)
			}
			// Only player 0 answers, after rtt.
			h.clock.Advance(rtt)
			c1.send(fsnp.NewExtMessage(fsnp.CmdPing, 0))
			h.waitPing(0, time.Duration(f/10)*rtt/pingWindow)
		}
	}
	s := h.g.Stats()
	if s.Players[0].PingAvg != rtt {
		t.Fatalf("player 0 ping avg = %v, want %v after 10 replies", s.Players[0].PingAvg, rtt)
	}
}

func TestUnansweredPingIsNotResent(t *testing.T) {
	h, c1, _ := startTwo(t)
	for f := uint32(2); f <= 20; f++ {
		h.tick()
		c1.expectFrame(f)
		if f == 10 {
			c1.expectExt(fsnp.CmdPing)
		}
	}
	c1.expectNothing() // no second PING at frame 20 while the first is outstanding
}

func TestWriterChunksLargeBuffers(t *testing.T) {
	server, clientSide := net.Pipe()
	c := newConn(server)
	done := make(chan struct{})
	go func() {
		c.writeLoop()
		close(done)
	}()
	payload := bytes.Repeat([]byte{0xAB}, 3*MaxSendChunk+10)
	c.out <- payload
	close(c.out)

	// net.Pipe hands each Write over as one Read, so the read sizes are
	// the write sizes.
	var got []byte
	buf := make([]byte, 64*1024)
	for {
		n, err := clientSide.Read(buf)
		if n > MaxSendChunk {
			t.Fatalf("single write of %d bytes exceeds MaxSendChunk %d", n, MaxSendChunk)
		}
		got = append(got, buf[:n]...)
		if err == io.EOF {
			break
		}
		if err != nil {
			t.Fatal(err)
		}
	}
	if !bytes.Equal(got, payload) {
		t.Fatalf("payload corrupted: got %d bytes, want %d", len(got), len(payload))
	}
	<-done
}

// TestReplayCapturedSession drives the game with the real client streams
// from internal/fsnp/testdata: every frame's RND_CHECK/MEM_CHECK/ack (and
// input events) as fs-uae v3.1.66 sent them. The server must run the whole
// session without a desync and with every common frame verified.
func TestReplayCapturedSession(t *testing.T) {
	groups := func(file string) [][]byte {
		raw, err := os.ReadFile(filepath.Join("..", "fsnp", "testdata", file))
		if err != nil {
			t.Fatal(err)
		}
		var out [][]byte
		start := 0
		for i := 0; i+4 <= len(raw); i += 4 {
			if fsnp.DecodeMessage(raw[i : i+4]).IsFrame() {
				out = append(out, raw[start:i+4])
				start = i + 4
			}
		}
		return out
	}
	g1 := groups("client1-to-server.bin")
	g2 := groups("client2-to-server.bin")
	n := min(len(g1), len(g2))
	if testing.Short() {
		n = min(n, 300)
	}

	h, c1, c2 := startTwo(t)
	for f := 1; f <= n; f++ {
		if f > 1 {
			h.clock.Tick(t)
		}
		c1.write(g1[f-1])
		c2.write(g2[f-1])
		h.waitFrames(uint32(f))
	}
	h.tick()
	s := h.g.Stats()
	if s.Verified != int64(n-1) {
		t.Fatalf("verified = %d, want %d", s.Verified, n-1)
	}
	select {
	case err := <-h.runErr:
		t.Fatalf("game stopped during replay: %v", err)
	default:
	}
	t.Logf("replayed %d frames, verified through tag %d", n, s.Verified)
}
