// Package game runs one FSNP netplay session: a single goroutine owns all
// game state and talks to per-connection reader and writer goroutines over
// channels. It reproduces the observable behaviour of launcher/server/game.py
// — see docs/netplay-go-server-design.md — without its shared-state locking.
package game

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"math/rand/v2"
	"net"
	"strings"
	"sync"
	"time"

	"github.com/pdabel/fs-uae-launcher/fsnp-server/internal/fsnp"
)

const (
	// FrameInterval is the server tick: one frame word per client every 20 ms.
	FrameInterval = 20 * time.Millisecond

	// DefaultMaxDrift is how many frames the slowest client may fall behind
	// before the server stops advancing until it catches up.
	DefaultMaxDrift = 25

	// MaxPlayers is fixed by the v3.1.66 client (PLAYER_TAG_0..5).
	MaxPlayers = 6

	// autoFlushCount matches game.py: a client's queue is flushed when it
	// reaches this many entries, independent of the tick.
	autoFlushCount = 100

	// ringSize is the depth of the per-player checksum and frame-time rings.
	ringSize = 100

	// pingWindow is how many round trips the reported ping is averaged over.
	pingWindow = 10

	// shutdownWriteTimeout bounds how long Run waits for writers to deliver
	// the final ERROR word before returning.
	shutdownWriteTimeout = 2 * time.Second

	eventQueueDepth = 256
)

// Config describes one game.
type Config struct {
	Players       int
	PasswordHash  uint32        // fsnp.PasswordHash of the game password
	LaunchTimeout time.Duration // give up if not all players have joined by then; 0 = never
	MaxDrift      uint32        // 0 = DefaultMaxDrift
	Clock         Clock         // nil = RealClock
	Logger        *slog.Logger  // nil = slog.Default()
}

// Errors returned by Run.
var (
	ErrLaunchTimeout = errors.New("game: not all players joined before the launch timeout")
	ErrDesync        = errors.New("game: players desynchronised")
)

// Game is one netplay session. Construct with New, then Run it; feed it
// connections with Serve or HandleConn.
type Game struct {
	cfg   Config
	clock Clock
	log   *slog.Logger

	events chan event
	done   chan struct{}

	// Everything below is owned by the Run goroutine.
	started         bool
	frame           uint32
	frameTimes      [ringSize]time.Time
	verified        int64 // highest checksum tag verified across all players
	stalled         bool
	stallTicks      int
	emulatorVersion [8]byte
	players         []*player // indexed by slot; nil = empty
	joined          int
	writers         sync.WaitGroup
	stop            *stopRequest
	ticker          Ticker
	ticks           <-chan time.Time
}

type stopRequest struct {
	code   byte // MESSAGE_ERROR code sent to every remaining player
	reason string
	err    error // what Run returns
}

// New creates a game that is not yet listening or running.
func New(cfg Config) (*Game, error) {
	if cfg.Players < 1 || cfg.Players > MaxPlayers {
		return nil, fmt.Errorf("game: players must be 1..%d, got %d", MaxPlayers, cfg.Players)
	}
	if cfg.MaxDrift == 0 {
		cfg.MaxDrift = DefaultMaxDrift
	}
	if cfg.Clock == nil {
		cfg.Clock = RealClock{}
	}
	if cfg.Logger == nil {
		cfg.Logger = slog.Default()
	}
	return &Game{
		cfg:      cfg,
		clock:    cfg.Clock,
		log:      cfg.Logger,
		events:   make(chan event, eventQueueDepth),
		done:     make(chan struct{}),
		verified: -1,
		players:  make([]*player, cfg.Players),
	}, nil
}

// Done is closed when Run has returned.
func (g *Game) Done() <-chan struct{} { return g.done }

// Serve accepts connections on ln and hands each to HandleConn until ctx is
// cancelled, the game ends, or Accept fails.
func (g *Game) Serve(ctx context.Context, ln net.Listener) error {
	go func() {
		select {
		case <-ctx.Done():
		case <-g.done:
		}
		_ = ln.Close()
	}()
	for {
		nc, err := ln.Accept()
		if err != nil {
			select {
			case <-ctx.Done():
				return nil
			case <-g.done:
				return nil
			default:
			}
			var ne net.Error
			if errors.As(err, &ne) && ne.Timeout() {
				continue
			}
			return err
		}
		go g.HandleConn(nc)
	}
}

// Run owns the game state until the game ends. It returns nil when the game
// ended normally (a player left, or ctx was cancelled), ErrLaunchTimeout, or
// ErrDesync.
func (g *Game) Run(ctx context.Context) error {
	defer close(g.done)

	var launchTimeout <-chan time.Time
	if g.cfg.LaunchTimeout > 0 {
		launchTimeout = g.clock.After(g.cfg.LaunchTimeout)
	}

	for g.stop == nil {
		select {
		case <-ctx.Done():
			g.stop = &stopRequest{code: fsnp.ErrGameStopped, reason: "shutdown requested"}
		case <-launchTimeout:
			if !g.started {
				g.stop = &stopRequest{code: fsnp.ErrGameStopped, reason: "launch timeout", err: ErrLaunchTimeout}
			}
			launchTimeout = nil
		case <-g.ticks:
			g.tick()
		case ev := <-g.events:
			g.handle(ev)
		}
	}
	g.shutdown()
	return g.stop.err
}

// Stats is a snapshot of the game as seen by its goroutine. Zero if the game
// has ended.
type Stats struct {
	Started  bool
	Frame    uint32
	Verified int64
	Stalled  bool
	Players  []PlayerStats
}

// PlayerStats is one player's slice of Stats.
type PlayerStats struct {
	Slot    int
	Tag     string
	Frame   uint32
	Lag     time.Duration
	PingAvg time.Duration
}

// Stats asks the game goroutine for a snapshot.
func (g *Game) Stats() Stats {
	reply := make(chan Stats, 1)
	if !g.post(event{kind: evStats, stats: reply}) {
		return Stats{}
	}
	select {
	case s := <-reply:
		return s
	case <-g.done:
		return Stats{}
	}
}

// post delivers an event to the game goroutine, returning false if the game
// has ended.
func (g *Game) post(ev event) bool {
	select {
	case g.events <- ev:
		return true
	case <-g.done:
		return false
	}
}

type eventKind int

const (
	evJoin eventKind = iota
	evAck
	evInput
	evMemCheck
	evRndCheck
	evPong
	evText
	evGone
	evStats
)

type event struct {
	kind  eventKind
	c     *conn
	data  uint32
	text  []byte
	err   error
	join  *joinRequest
	stats chan Stats
}

type joinRequest struct {
	hs    fsnp.Handshake
	reply chan joinReply
}

type joinReply struct {
	errCode byte // 0 = joined
}

type check struct {
	data  uint32
	frame uint32
}

type player struct {
	slot       int
	tag        [3]byte
	sessionKey uint32
	c          *conn

	frame    uint32
	lag      time.Duration
	memCheck [ringSize]check
	rndCheck [ringSize]check

	pingSentAt time.Time // zero = no ping outstanding
	pings      [pingWindow]time.Duration
	pingIdx    int
	pingSum    time.Duration

	pending      []byte
	pendingCount int
}

// tagString is the player's tag without the NUL padding a short tag carries
// on the wire.
func (p *player) tagString() string { return strings.TrimRight(string(p.tag[:]), "\x00") }

func (p *player) logAttrs() []any {
	return []any{"player", p.slot, "tag", p.tagString()}
}

// queue appends one word to the player's outgoing buffer.
func (p *player) queue(m fsnp.Message) {
	w := m.Encode()
	p.queueBytes(w[:])
}

// queueBytes appends one entry (a word, or a TEXT word plus payload) to the
// outgoing buffer.
func (p *player) queueBytes(b []byte) {
	p.pending = append(p.pending, b...)
	p.pendingCount++
}

func (g *Game) handle(ev event) {
	if ev.kind == evStats {
		ev.stats <- g.snapshot()
		return
	}
	if ev.kind == evJoin {
		ev.join.reply <- joinReply{errCode: g.join(ev.c, ev.join.hs)}
		return
	}
	p := g.playerOf(ev.c)
	if p == nil {
		// A connection that was already dropped, or never joined.
		return
	}
	switch ev.kind {
	case evAck:
		g.onAck(p, ev.data)
	case evInput:
		g.onInput(p, ev.data)
	case evMemCheck:
		p.memCheck[p.frame%ringSize] = check{ev.data, p.frame}
	case evRndCheck:
		p.rndCheck[p.frame%ringSize] = check{ev.data, p.frame}
	case evPong:
		g.onPong(p)
	case evText:
		g.onText(p, ev.text)
	case evGone:
		g.onGone(p, ev.err)
	}
}

func (g *Game) playerOf(c *conn) *player {
	for _, p := range g.players {
		if p != nil && p.c == c {
			return p
		}
	}
	return nil
}

func (g *Game) livePlayers() []*player {
	out := make([]*player, 0, len(g.players))
	for _, p := range g.players {
		if p != nil {
			out = append(out, p)
		}
	}
	return out
}

// join applies game.py's Game.add_client rules and, on success, sends the
// handshake response: SESSION_KEY, PLAYERS, then one PLAYER_TAG_n for every
// player joined so far (that last part is what makes the tag-broadcast count
// depend on join order — see TestTagBroadcastAsymmetry in internal/fsnp).
func (g *Game) join(c *conn, hs fsnp.Handshake) byte {
	log := g.log.With("addr", c.addr, "tag", strings.TrimRight(string(hs.Tag[:]), "\x00"))
	if hs.Player != fsnp.NewPlayerByte {
		// Rejoin of an existing slot. The client never does this today
		// (design doc: "server-side resume is dead code until the client is
		// changed"), so validate it the way game.py does and then refuse.
		// Phase three swaps the connection in and replays from the ring.
		if int(hs.Player) >= len(g.players) || g.players[hs.Player] == nil {
			return fsnp.ErrPlayerNumber
		}
		if g.players[hs.Player].sessionKey != hs.SessionKey {
			return fsnp.ErrSessionKey
		}
		log.Warn("rejoin not supported", "player", hs.Player, "resume_from", hs.ResumeFromPacket)
		return fsnp.ErrCannotResume
	}
	if hs.ResumeFromPacket != 0 {
		return fsnp.ErrClientError
	}
	if g.started {
		return fsnp.ErrGameAlreadyStarted
	}
	slot := -1
	for i, p := range g.players {
		if p == nil {
			slot = i
			break
		}
	}
	if slot < 0 {
		return fsnp.ErrGameAlreadyStarted
	}
	if g.joined == 0 {
		g.emulatorVersion = hs.EmulatorVersion
	} else if g.emulatorVersion != hs.EmulatorVersion {
		log.Warn("emulator version mismatch",
			"want", fmt.Sprintf("%x", g.emulatorVersion), "got", fmt.Sprintf("%x", hs.EmulatorVersion))
		return fsnp.ErrEmulatorMismatch
	}

	p := &player{
		slot:       slot,
		tag:        hs.Tag,
		sessionKey: rand.Uint32N(1 << 24),
		c:          c,
	}
	g.players[slot] = p
	g.joined++
	g.writers.Add(1)
	go func() {
		defer g.writers.Done()
		c.writeLoop()
	}()
	log.Info("player joined", "player", slot, "joined", g.joined, "players", g.cfg.Players)

	p.queue(fsnp.NewExtMessage(fsnp.CmdSessionKey, p.sessionKey))
	p.queue(fsnp.NewExtMessage(fsnp.CmdPlayers, uint32(slot)<<8|uint32(g.cfg.Players)))
	g.queueTags(p)
	g.flush(p)

	if g.joined == g.cfg.Players {
		g.start()
	}
	return 0
}

func (g *Game) queueTags(to *player) {
	for i, p := range g.players {
		if p == nil {
			continue
		}
		data := uint32(p.tag[0])<<16 | uint32(p.tag[1])<<8 | uint32(p.tag[2])
		to.queue(fsnp.NewExtMessage(byte(fsnp.CmdPlayerTag0+i), data))
	}
}

// start mirrors the top of game.py's __game_loop: every player gets every
// tag again (queued, not flushed — they ride out with the first frame word),
// then the tick starts.
func (g *Game) start() {
	g.started = true
	for _, p := range g.livePlayers() {
		g.queueTags(p)
	}
	g.ticker = g.clock.NewTicker(FrameInterval)
	g.ticks = g.ticker.C()
	g.log.Info("all players joined, starting game", "players", g.cfg.Players)
}

// flush hands the player's pending buffer to its writer. A writer whose
// queue is full is not keeping up with 50 flushes a second; that player is
// dropped rather than letting it block the tick.
func (g *Game) flush(p *player) {
	if len(p.pending) == 0 || g.players[p.slot] != p {
		// Nothing to send, or the player was dropped earlier in this same
		// broadcast and its out channel is already closed.
		return
	}
	buf := p.pending
	p.pending = nil
	p.pendingCount = 0
	select {
	case p.c.out <- buf:
	default:
		g.onGone(p, errors.New("writer queue full"))
	}
}

// broadcast queues one word to every live player, flushing any whose queue
// hits autoFlushCount, exactly as game.py's queue_message does.
func (g *Game) broadcast(m fsnp.Message) {
	w := m.Encode()
	g.broadcastBytes(w[:])
}

func (g *Game) broadcastBytes(b []byte) {
	for _, p := range g.livePlayers() {
		p.queueBytes(b)
		if p.pendingCount == autoFlushCount {
			g.flush(p)
		}
	}
}

// sendError puts a MESSAGE_ERROR word ahead of anything already queued and
// flushes, matching game.py's send_error_message writing straight to the
// socket past the queue.
func (g *Game) sendError(p *player, code byte) {
	w := fsnp.NewExtMessage(fsnp.CmdError, uint32(code)).Encode()
	p.pending = append(w[:], p.pending...)
	p.pendingCount++
	g.flush(p)
}

func (g *Game) onAck(p *player, frame uint32) {
	if frame != p.frame+1 {
		g.log.Warn("unexpected frame ack", append(p.logAttrs(), "want", p.frame+1, "got", frame)...)
	}
	p.frame = frame
	p.lag = g.clock.Now().Sub(g.frameTimes[frame%ringSize])
}

func (g *Game) onInput(p *player, ev uint32) {
	if !g.started {
		g.log.Warn("game not started, ignoring input event", append(p.logAttrs(), "event", fmt.Sprintf("%06x", ev))...)
		return
	}
	// Broadcast to everyone, the sender included — the emulator relies on
	// seeing its own events echoed.
	g.broadcast(fsnp.NewInputMessage(ev))
}

func (g *Game) onPong(p *player) {
	if p.pingSentAt.IsZero() {
		return
	}
	rtt := g.clock.Now().Sub(p.pingSentAt)
	p.pingSum += rtt - p.pings[p.pingIdx]
	p.pings[p.pingIdx] = rtt
	p.pingIdx = (p.pingIdx + 1) % pingWindow
	p.pingSentAt = time.Time{}
}

func (p *player) pingAvg() time.Duration { return p.pingSum / pingWindow }

func (g *Game) onText(from *player, text []byte) {
	g.log.Info("text message", append(from.logAttrs(), "text", string(text))...)
	g.broadcastText(from.slot, text)
}

func (g *Game) broadcastText(fromSlot int, text []byte) {
	w := fsnp.NewExtMessage(fsnp.CmdText, uint32(fromSlot)<<16|uint32(len(text))).Encode()
	g.broadcastBytes(append(w[:], text...))
}

// onGone handles a player's connection failing. Before the game starts the
// slot is simply freed for the next joiner; after it starts the session ends
// for everyone (phase one — phase three adds a reconnect grace window).
func (g *Game) onGone(p *player, err error) {
	if g.players[p.slot] != p {
		return
	}
	g.log.Info("player disconnected", append(p.logAttrs(), "err", err)...)
	g.players[p.slot] = nil
	g.joined--
	close(p.c.out)
	if !g.started {
		return
	}
	g.broadcastText(p.slot, []byte(p.tagString()+" disconnected"))
	if g.stop == nil {
		g.stop = &stopRequest{code: fsnp.ErrGameStopped, reason: "player " + p.tagString() + " left"}
	}
}

// tick is one 20 ms iteration of game.py's __game_loop_iteration.
func (g *Game) tick() {
	if g.stalled {
		if g.oldestFrame() < g.frame {
			g.stallTicks++
			if g.stallTicks%100 == 0 {
				g.log.Info("still waiting for players", "frame", g.frame, "acked", g.ackedFrames())
			}
			return
		}
		g.stalled = false
		g.log.Info("players caught up", "frame", g.frame, "stall_ticks", g.stallTicks)
	}
	if g.frame%100 == 0 {
		g.sendStatus()
	}
	g.frame++
	now := g.clock.Now()
	g.frameTimes[g.frame%ringSize] = now
	fw := fsnp.NewFrameMessage(g.frame)
	for _, p := range g.livePlayers() {
		p.queue(fw)
		g.flush(p)
	}
	if g.frame%10 == 0 {
		for _, p := range g.livePlayers() {
			if p.pingSentAt.IsZero() {
				p.pingSentAt = now
				p.queue(fsnp.NewExtMessage(fsnp.CmdPing, 0))
				g.flush(p)
			}
		}
	}
	if g.frame%200 == 0 {
		for _, p := range g.livePlayers() {
			g.log.Info("status", append(p.logAttrs(),
				"frame", p.frame, "ping_ms", p.pingAvg().Milliseconds(), "lag_ms", p.lag.Milliseconds())...)
		}
	}
	g.checkGame()
}

// sendStatus queues PLAYER_LAG and PLAYER_PING for every player to every
// player, once per 100 frames.
func (g *Game) sendStatus() {
	for _, p := range g.livePlayers() {
		lag := uint32(p.lag.Milliseconds()) & 0xFFFF
		g.broadcast(fsnp.NewExtMessage(fsnp.CmdPlayerLag, uint32(p.slot)<<16|lag))
		ping := uint32(p.pingAvg().Milliseconds()) & 0xFFFF
		g.broadcast(fsnp.NewExtMessage(fsnp.CmdPlayerPing, uint32(p.slot)<<16|ping))
	}
}

func (g *Game) oldestFrame() uint32 {
	oldest := g.frame
	for _, p := range g.livePlayers() {
		if p.frame < oldest {
			oldest = p.frame
		}
	}
	return oldest
}

func (g *Game) ackedFrames() []uint32 {
	out := make([]uint32, 0, len(g.players))
	for _, p := range g.livePlayers() {
		out = append(out, p.frame)
	}
	return out
}

// checkGame verifies checksums for every tag all players have passed, then
// decides whether to stall. Checks for frame f arrive tagged f-1 (they are
// sent before the ack for f), so tag k is verifiable once every player has
// acked at least k+1 — i.e. once k < oldestFrame().
//
// game.py's __check_game advanced verified_frame even when
// check_synchronization returned early because a player was still at the
// frame being checked, so in steady state it skipped almost every frame.
// This is the rule it was reaching for.
func (g *Game) checkGame() {
	oldest := g.oldestFrame()
	for g.verified+1 < int64(oldest) {
		k := uint32(g.verified + 1)
		if !g.checkSync(k) {
			return
		}
		g.verified = int64(k)
	}
	if g.frame-oldest > g.cfg.MaxDrift {
		g.stalled = true
		g.stallTicks = 0
		g.log.Info("waiting for players", "frame", g.frame, "acked", g.ackedFrames())
	}
}

// checkSync compares every player's MEM_CHECK and RND_CHECK tagged with
// frame k. On mismatch it logs each player's value, requests shutdown with
// the matching desync error, and returns false.
func (g *Game) checkSync(k uint32) bool {
	players := g.livePlayers()
	if len(players) == 0 {
		return true
	}
	idx := k % ringSize
	kinds := []struct {
		name string
		get  func(*player) check
		code byte
	}{
		{"mem", func(p *player) check { return p.memCheck[idx] }, fsnp.ErrMemoryDesync},
		{"rnd", func(p *player) check { return p.rndCheck[idx] }, fsnp.ErrRandomDesync},
	}
	for _, kind := range kinds {
		want := kind.get(players[0])
		for _, p := range players[1:] {
			if kind.get(p) == want {
				continue
			}
			g.log.Error(kind.name+" check failed", "frame", k)
			for _, q := range players {
				c := kind.get(q)
				g.log.Error(kind.name+" check value", append(q.logAttrs(),
					"value", fmt.Sprintf("%06x", c.data), "tagged_frame", c.frame)...)
			}
			g.stop = &stopRequest{code: kind.code, reason: kind.name + " check failed", err: ErrDesync}
			return false
		}
	}
	return true
}

// shutdown sends the stop code to every remaining player, closes their
// writers, and waits (briefly) for the final bytes to go out.
func (g *Game) shutdown() {
	g.log.Info("stopping game", "reason", g.stop.reason, "frame", g.frame)
	if g.ticker != nil {
		g.ticker.Stop()
	}
	for _, p := range g.livePlayers() {
		g.sendError(p, g.stop.code)
		if g.players[p.slot] == p { // flush may have dropped it
			g.players[p.slot] = nil
			close(p.c.out)
		}
	}
	finished := make(chan struct{})
	go func() {
		g.writers.Wait()
		close(finished)
	}()
	select {
	case <-finished:
	case <-time.After(shutdownWriteTimeout):
		g.log.Warn("timed out waiting for writers to finish")
	}
}

func (g *Game) snapshot() Stats {
	s := Stats{
		Started:  g.started,
		Frame:    g.frame,
		Verified: g.verified,
		Stalled:  g.stalled,
	}
	for _, p := range g.livePlayers() {
		s.Players = append(s.Players, PlayerStats{
			Slot:    p.slot,
			Tag:     p.tagString(),
			Frame:   p.frame,
			Lag:     p.lag,
			PingAvg: p.pingAvg(),
		})
	}
	return s
}
