// Package lobby hosts many FSNP games behind one port. The HTTP API that
// creates games and the games themselves share the listener: the first four
// bytes of each connection pick HTTP, the PING probe or an FSNP handshake,
// and an FSNP handshake is routed to its game by password hash. The lobby
// keeps those hashes unique across live games, which is what makes the
// password a game's address — see "Many games per process" in
// docs/netplay-go-server-design.md.
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

	// DefaultLaunchTimeout reaps a game whose players have not all joined.
	// Long enough to agree a config over IRC before anyone starts FS-UAE.
	DefaultLaunchTimeout = 15 * time.Minute

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
	LaunchTimeout   time.Duration // per game; 0 = DefaultLaunchTimeout
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
	ErrClosed         = errors.New("lobby: shutting down")
)

// Info is what Create reports about a new game.
type Info struct {
	ID       string
	Password string
	Players  int
}

// Lobby is a registry of live games, keyed by id and by password hash.
// The games' own state is owned by their goroutines as always; the mutex
// guards only the two maps and the closed flag.
type Lobby struct {
	cfg Config
	log *slog.Logger

	ctx    context.Context // parent of every game; cancelled on shutdown
	cancel context.CancelFunc
	wg     sync.WaitGroup // one per running game

	mu     sync.Mutex
	closed bool
	byID   map[string]*entry
	byHash map[uint32]*entry
}

type entry struct {
	id   string
	hash uint32
	g    *game.Game
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

// Create starts a game for players players. An empty password means the
// lobby generates one: a lobby game can't be passwordless, because the hash
// is how a connection finds its game. A supplied password whose hash matches
// a live game's is refused with ErrPasswordInUse.
func (l *Lobby) Create(players int, password string) (Info, error) {
	if len(password) > MaxPasswordLength {
		return Info{}, ErrPasswordLength
	}
	generated := password == ""

	l.mu.Lock()
	defer l.mu.Unlock()
	if l.closed {
		return Info{}, ErrClosed
	}
	if len(l.byID) >= l.cfg.MaxGames {
		return Info{}, ErrFull
	}
	if generated {
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
		return Info{}, ErrPasswordInUse
	}

	id := newID()
	g, err := game.New(game.Config{
		Players:       players,
		PasswordHash:  hash,
		LaunchTimeout: l.cfg.LaunchTimeout,
		Clock:         l.cfg.Clock,
		Logger:        l.log.With("game", id),
		LogInput:      l.cfg.LogInput,
	})
	if err != nil {
		return Info{}, err
	}
	e := &entry{id: id, hash: hash, g: g}
	l.byID[id] = e
	l.byHash[hash] = e
	l.wg.Add(1)
	go l.run(e)

	l.log.Info("game created", "game", id, "players", players,
		"password_generated", generated, "games", len(l.byID))
	return Info{ID: id, Password: password, Players: players}, nil
}

// run owns one game's lifetime and removes it from the registry when it
// ends, for any reason, so its password can address a new game.
func (l *Lobby) run(e *entry) {
	defer l.wg.Done()
	err := e.g.Run(l.ctx)

	l.mu.Lock()
	delete(l.byID, e.id)
	delete(l.byHash, e.hash)
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

// lookup returns the live game whose password hashes to hash, or nil.
func (l *Lobby) lookup(hash uint32) *game.Game {
	l.mu.Lock()
	defer l.mu.Unlock()
	if e := l.byHash[hash]; e != nil {
		return e.g
	}
	return nil
}

// Len reports how many games are live.
func (l *Lobby) Len() int {
	l.mu.Lock()
	defer l.mu.Unlock()
	return len(l.byID)
}

// shutdown refuses further games, stops every live one (each sends
// ERROR_GAME_STOPPED to its players) and waits for them to finish.
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
