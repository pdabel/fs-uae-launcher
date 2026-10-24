// Package lobby hosts many FSNP games behind one port. The HTTP API that
// creates games and the games themselves share the listener: the first four
// bytes of each connection pick HTTP, the PING probe or an FSNP handshake,
// and an FSNP handshake is routed to its game by password hash. The lobby
// keeps those hashes unique across live games, which is what makes the
// password a game's address — see "Many games per process" in
// docs/netplay-go-server-design.md.
//
// A game created with POST /game also holds its session before it starts:
// the players who have joined, the config document and who has applied it.
// Its password hash is reserved at create but routed only at start, when the
// FSNP game runs — see "Future: the session owns the config".
package lobby

import (
	"context"
	"crypto/rand"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/pdabel/fs-uae-launcher/fsnp-server/internal/fsnp"
	"github.com/pdabel/fs-uae-launcher/fsnp-server/internal/game"
)

const (
	// DefaultMaxGames bounds how many games may be live at once.
	DefaultMaxGames = 64

	// DefaultLaunchTimeout reaps a running game whose players have not all
	// joined. A game from /game/create runs from the moment it is created,
	// so this is also how long its players have to agree a config over IRC;
	// a session game runs from its start, when every launcher is ready.
	DefaultLaunchTimeout = 15 * time.Minute

	// DefaultIdleTimeout reaps a session game that nobody has touched — no
	// join, config, ready or poll — before it started.
	DefaultIdleTimeout = 10 * time.Minute

	// MaxPasswordLength caps a password supplied to /game/create.
	MaxPasswordLength = 128

	// generatedPasswordLength is 40 bits from a 32-symbol alphabet.
	generatedPasswordLength = 8

	// passwordAlphabet has 32 symbols, so a random byte maps onto it without
	// bias, and leaves out l/o/0/1 since the password is shown in the
	// channel and may be read aloud or retyped.
	passwordAlphabet = "abcdefghijkmnpqrstuvwxyz23456789"
)

// Config describes a lobby.
type Config struct {
	MaxGames        int           // 0 = DefaultMaxGames
	LaunchTimeout   time.Duration // per game, from when it runs; 0 = DefaultLaunchTimeout
	IdleTimeout     time.Duration // per session game before start; 0 = DefaultIdleTimeout
	PublicAddresses []string      // reported to clients; empty = the request's Host
	Clock           game.Clock    // nil = game.RealClock, passed to every game
	Logger          *slog.Logger  // nil = slog.Default()
	LogInput        bool          // passed to every game
}

// Errors returned by Create.
var (
	ErrFull           = errors.New("lobby: too many games")
	ErrPasswordInUse  = errors.New("lobby: a live game already uses that password")
	ErrPasswordLength = fmt.Errorf("lobby: password longer than %d bytes", MaxPasswordLength)
	ErrPlayers        = fmt.Errorf("lobby: players must be 1..%d", game.MaxPlayers)
	ErrClosed         = errors.New("lobby: shutting down")
)

// Info is what Create reports about a new game.
type Info struct {
	ID       string
	Password string
	Players  int
}

// Lobby is a registry of live games, keyed by id and by password hash.
// A running game's own state is owned by its goroutine as always; the mutex
// guards the two maps, the closed flag, and every entry's session state.
type Lobby struct {
	cfg Config
	log *slog.Logger

	ctx    context.Context // parent of every game; cancelled on shutdown
	cancel context.CancelFunc
	wg     sync.WaitGroup // one per running game and per idle reaper

	mu     sync.Mutex
	closed bool
	byID   map[string]*entry
	byHash map[uint32]*entry // reserved hashes; routed only once entry.g is set
}

// New creates a lobby. It hosts nothing until Serve is called, but Create
// works as soon as it returns.
func New(cfg Config) *Lobby {
	if cfg.MaxGames <= 0 {
		cfg.MaxGames = DefaultMaxGames
	}
	if cfg.LaunchTimeout <= 0 {
		cfg.LaunchTimeout = DefaultLaunchTimeout
	}
	if cfg.IdleTimeout <= 0 {
		cfg.IdleTimeout = DefaultIdleTimeout
	}
	if cfg.Clock == nil {
		cfg.Clock = game.RealClock{}
	}
	if cfg.Logger == nil {
		cfg.Logger = slog.Default()
	}
	ctx, cancel := context.WithCancel(context.Background())
	return &Lobby{
		cfg:    cfg,
		log:    cfg.Logger,
		ctx:    ctx,
		cancel: cancel,
		byID:   make(map[string]*entry),
		byHash: make(map[uint32]*entry),
	}
}

// Create starts a game for players players, routable at once: the
// /game/create path, where the config is agreed over IRC. An empty password
// means the lobby generates one: a lobby game can't be passwordless, because
// the hash is how a connection finds its game. A supplied password whose
// hash matches a live game's is refused with ErrPasswordInUse.
func (l *Lobby) Create(players int, password string) (Info, error) {
	l.mu.Lock()
	defer l.mu.Unlock()
	e, err := l.reserveLocked(players, password)
	if err != nil {
		return Info{}, err
	}
	l.startLocked(e)
	l.log.Info("game created", "game", e.id, "players", players,
		"password_generated", password == "", "games", len(l.byID))
	return Info{ID: e.id, Password: e.password, Players: players}, nil
}

// reserveLocked registers a game that isn't routable yet: its id and
// password hash are taken, so uniqueness is settled now, but no FSNP
// connection reaches it until startLocked. l.mu must be held.
func (l *Lobby) reserveLocked(players int, password string) (*entry, error) {
	if players < 1 || players > game.MaxPlayers {
		return nil, ErrPlayers
	}
	if len(password) > MaxPasswordLength {
		return nil, ErrPasswordLength
	}
	if l.closed {
		return nil, ErrClosed
	}
	if len(l.byID) >= l.cfg.MaxGames {
		return nil, ErrFull
	}
	if password == "" {
		for {
			password = newPassword()
			if _, taken := l.byHash[fsnp.PasswordHash(password)]; !taken {
				break
			}
		}
	}
	hash := fsnp.ExpectedPasswordHash(password)
	if _, taken := l.byHash[hash]; taken || hash == 0 {
		// Hash 0 is what every passwordless client sends, so it can never
		// address one game. Only a 1-in-2^32 password can produce it.
		return nil, ErrPasswordInUse
	}

	e := newEntry(newID(), hash, password, players)
	l.byID[e.id] = e
	l.byHash[hash] = e
	return e, nil
}

// startLocked makes e routable and runs its FSNP game, whose launch timeout
// counts from now. l.mu must be held.
func (l *Lobby) startLocked(e *entry) {
	g, err := game.New(game.Config{
		Players:       e.players,
		PasswordHash:  e.hash,
		LaunchTimeout: l.cfg.LaunchTimeout,
		Clock:         l.cfg.Clock,
		Logger:        l.log.With("game", e.id),
		LogInput:      l.cfg.LogInput,
	})
	if err != nil {
		// reserveLocked checked the only thing game.New refuses.
		panic(err)
	}
	ctx, cancel := context.WithCancel(l.ctx)
	e.g = g
	e.stopGame = cancel
	e.stopReaper()
	e.changedLocked()
	l.wg.Add(1)
	go l.run(e, ctx)
}

// run owns one game's lifetime and removes it from the registry when it
// ends, for any reason, so its password can address a new game.
func (l *Lobby) run(e *entry, ctx context.Context) {
	defer l.wg.Done()
	err := e.g.Run(ctx)
	e.stopGame()

	l.mu.Lock()
	l.removeLocked(e)
	left := len(l.byID)
	l.mu.Unlock()

	log := l.log.With("game", e.id, "games", left)
	switch {
	case err == nil:
		log.Info("game ended")
	case errors.Is(err, game.ErrLaunchTimeout):
		log.Info("game reaped", "err", err)
	case errors.Is(err, game.ErrDesync):
		log.Warn("game ended with a desync", "err", err)
	default:
		log.Error("game failed", "err", err)
	}
}

// reap ends a session game that sits untouched for IdleTimeout before it
// starts. Every touch restarts the wait.
func (l *Lobby) reap(e *entry) {
	defer l.wg.Done()
	for {
		l.mu.Lock()
		seen := e.touches
		l.mu.Unlock()
		select {
		case <-e.activity:
		case <-e.reaperDone:
			return
		case <-l.ctx.Done():
			l.mu.Lock()
			l.removeLocked(e)
			l.mu.Unlock()
			return
		case <-l.cfg.Clock.After(l.cfg.IdleTimeout):
			l.mu.Lock()
			if e.touches != seen {
				// Touched as the wait ran out — select chose the timer,
				// or the touch came while this waited for the lock.
				l.mu.Unlock()
				continue
			}
			reaped := e.g == nil && !e.ended
			if reaped {
				l.removeLocked(e)
			}
			left := len(l.byID)
			l.mu.Unlock()
			if reaped {
				l.log.Info("game reaped before start", "game", e.id,
					"idle", l.cfg.IdleTimeout, "games", left)
			}
			return
		}
	}
}

// endLocked stops e: a running game is cancelled, and removes itself as it
// finishes; one that hasn't started is removed now. l.mu must be held.
func (l *Lobby) endLocked(e *entry) {
	if e.g != nil {
		e.stopGame()
		return
	}
	l.removeLocked(e)
}

// removeLocked takes e out of the registry and marks it ended, waking
// anyone long-polling it. Idempotent. l.mu must be held.
func (l *Lobby) removeLocked(e *entry) {
	if e.ended {
		return
	}
	if l.byID[e.id] == e {
		delete(l.byID, e.id)
	}
	if l.byHash[e.hash] == e {
		delete(l.byHash, e.hash)
	}
	e.ended = true
	e.stopReaper()
	e.changedLocked()
}

// lookup returns the running game whose password hash is hash, or nil. A
// reserved hash whose game hasn't started routes nowhere.
func (l *Lobby) lookup(hash uint32) *game.Game {
	l.mu.Lock()
	defer l.mu.Unlock()
	if e := l.byHash[hash]; e != nil {
		return e.g
	}
	return nil
}

// Len reports how many games are live, started or not.
func (l *Lobby) Len() int {
	l.mu.Lock()
	defer l.mu.Unlock()
	return len(l.byID)
}

// shutdown refuses further games, stops every live one (each running game
// sends ERROR_GAME_STOPPED to its players) and waits for them to finish.
func (l *Lobby) shutdown() {
	l.mu.Lock()
	l.closed = true
	l.mu.Unlock()
	l.cancel()
	l.wg.Wait()
}

func newPassword() string {
	var b [generatedPasswordLength]byte
	if _, err := rand.Read(b[:]); err != nil {
		panic(err) // crypto/rand does not fail on supported platforms
	}
	for i := range b {
		b[i] = passwordAlphabet[b[i]%byte(len(passwordAlphabet))]
	}
	return string(b[:])
}

// newID returns a random UUIDv4, the same shape /hostgame puts in
// __netplay_game.
func newID() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		panic(err)
	}
	b[6] = b[6]&0x0f | 0x40
	b[8] = b[8]&0x3f | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

// newToken returns 128 random bits as hex, for host and player tokens.
func newToken() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		panic(err)
	}
	return fmt.Sprintf("%x", b)
}
