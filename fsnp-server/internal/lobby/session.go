package lobby

import (
	"context"
	"crypto/subtle"
	"errors"
	"fmt"
	"strconv"
	"strings"

	"github.com/pdabel/fs-uae-launcher/fsnp-server/internal/game"
)

// State is a game's place in its lifecycle, as GET /game/{id} reports it.
type State string

const (
	StateCreated     State = "created"     // no config yet
	StateConfiguring State = "configuring" // config set, not every slot ready
	StateReady       State = "ready"       // every slot claimed and ready: start is allowed
	StateRunning     State = "running"     // FSNP game routed and running: launch fs-uae
	StateEnded       State = "ended"
)

// Slot statuses, per claimed slot, against the current config.
const (
	SlotEmpty    = "empty"    // not claimed
	SlotWaiting  = "waiting"  // claimed, nothing reported for this config version
	SlotReady    = "ready"    // applied it, same hash, nothing missing
	SlotMissing  = "missing"  // applied it but couldn't find some files
	SlotMismatch = "mismatch" // applied it and got a different hash
)

// Limits on what a session accepts. The config is a few hundred short
// strings; these leave ample room and bound what one game can hold.
const (
	maxKeys        = 1024
	maxKeyLength   = 128
	maxValueLength = 4096
	maxTagLength   = 32
	maxHashLength  = 64
)

// The keys the server writes into every document itself: each is a fact
// about the game the server already holds, so a host can't send a document
// that disagrees with the game it describes. The rest of the vocabulary is
// the launcher's, handed over as opaque key lists at create.
const (
	keyGame      = "__netplay_game"
	keyPassword  = "__netplay_password"
	keyPlayers   = "__netplay_players"
	keyPort      = "__netplay_port"
	keyAddresses = "__netplay_addresses"
)

var serverOwnedKeys = []string{keyGame, keyPassword, keyPlayers, keyPort, keyAddresses}

// Session errors; the HTTP layer maps each to a status.
var (
	errNotFound   = errors.New("no such game")
	errForbidden  = errors.New("token does not authorise this call")
	errStarted    = errors.New("game has already started")
	errSlotsFull  = errors.New("every slot is taken")
	errNoConfig   = errors.New("the host has not sent a config yet")
	errStale      = errors.New("config has changed since that version")
	errNotReady   = errors.New("not every slot is claimed and ready")
	errHostSlot   = errors.New("slot 0 is the host's; end the game instead")
	errNoSuchSlot = errors.New("no such slot")
)

// invalidError is a request the server won't accept as sent (400).
type invalidError struct{ msg string }

func (e invalidError) Error() string { return e.msg }

func invalid(format string, args ...any) error {
	return invalidError{fmt.Sprintf(format, args...)}
}

// KeyLists is the launcher's config vocabulary for one game: the keys a
// document may carry, and the ordered list the hash runs over (duplicates
// and all — see game.ConfigHash).
type KeyLists struct {
	Sync     []string `json:"sync"`
	Checksum []string `json:"checksum"`
}

// entry is one live game: its address in the router, and, for a game
// created with POST /game, its session. Everything mutable is guarded by
// Lobby.mu.
type entry struct {
	id       string
	hash     uint32
	password string
	players  int

	// Set by startLocked; nil until the game runs.
	g        *game.Game
	stopGame context.CancelFunc

	ended bool

	// Session state. A /game/create game starts at once and has none of it.
	port          string
	addresses     []string
	hostToken     string
	keys          KeyLists
	syncSet       map[string]bool
	config        map[string]string // nil until the host sends one; replaced, never mutated
	configVersion uint64
	configHash    string
	slots         []slot

	// revision counts every change a poller could see; changed is closed
	// and replaced on each one, to wake long-polls.
	revision uint64
	changed  chan struct{}

	activity      chan struct{} // nudges the idle reaper; buffered 1
	touches       uint64        // counts touches, so the reaper can tell one raced its timer
	reaperDone    chan struct{} // closed at start or removal
	reaperStopped bool
}

type slot struct {
	claimed bool
	tag     string
	token   string
	ready   *readyReport // nil until reported for the current config
}

type readyReport struct {
	configVersion uint64
	hash          string
	missing       map[string]string // replaced, never mutated
}

func newEntry(id string, hash uint32, password string, players int) *entry {
	return &entry{
		id:         id,
		hash:       hash,
		password:   password,
		players:    players,
		slots:      make([]slot, players),
		revision:   1,
		changed:    make(chan struct{}),
		activity:   make(chan struct{}, 1),
		reaperDone: make(chan struct{}),
	}
}

// changedLocked records a change and wakes every long-poll.
func (e *entry) changedLocked() {
	e.revision++
	close(e.changed)
	e.changed = make(chan struct{})
}

// touch restarts the idle wait. l.mu must be held.
func (e *entry) touch() {
	e.touches++
	select {
	case e.activity <- struct{}{}:
	default:
	}
}

func (e *entry) stopReaper() {
	if !e.reaperStopped {
		e.reaperStopped = true
		close(e.reaperDone)
	}
}

func (e *entry) stateLocked() State {
	switch {
	case e.ended:
		return StateEnded
	case e.g != nil:
		return StateRunning
	case e.config == nil:
		return StateCreated
	}
	for _, s := range e.slots {
		if e.slotStatusLocked(s) != SlotReady {
			return StateConfiguring
		}
	}
	return StateReady
}

func (e *entry) slotStatusLocked(s slot) string {
	switch {
	case !s.claimed:
		return SlotEmpty
	case e.config == nil || s.ready == nil || s.ready.configVersion != e.configVersion:
		return SlotWaiting
	case len(s.ready.missing) > 0:
		// A missing file is cleared locally, so the hash differs too; the
		// missing file is the cause, and the one the player can act on.
		return SlotMissing
	case s.ready.hash != e.configHash:
		return SlotMismatch
	}
	return SlotReady
}

// serverValues are the server-owned keys' values for this game.
func (e *entry) serverValues() map[string]string {
	return map[string]string{
		keyGame:      e.id,
		keyPassword:  e.password,
		keyPlayers:   strconv.Itoa(e.players),
		keyPort:      e.port,
		keyAddresses: strings.Join(e.addresses, ","),
	}
}

// tokenMatches compares in constant time. An empty token never matches, so
// a /game/create game, which has no tokens, can't be driven over the
// session API.
func tokenMatches(want, got string) bool {
	return want != "" && subtle.ConstantTimeCompare([]byte(want), []byte(got)) == 1
}

func (e *entry) isHostLocked(token string) bool { return tokenMatches(e.hostToken, token) }

// Snapshot is GET /game/{id}'s body.
type Snapshot struct {
	ID            string            `json:"id"`
	State         State             `json:"state"`
	Revision      uint64            `json:"revision"`
	Players       int               `json:"players"`
	Port          string            `json:"port"`
	Addresses     []string          `json:"addresses"`
	Keys          KeyLists          `json:"keys"`
	ConfigVersion uint64            `json:"config_version"`
	Config        map[string]string `json:"config"`
	Hash          string            `json:"hash"`
	Slots         []SlotSnapshot    `json:"slots"`
}

// SlotSnapshot is one slot in a Snapshot.
type SlotSnapshot struct {
	Slot    int               `json:"slot"`
	Status  string            `json:"status"`
	Tag     string            `json:"tag,omitempty"`
	Hash    string            `json:"hash,omitempty"`    // what the player reported, for the current config
	Missing map[string]string `json:"missing,omitempty"` // SHA-1 key → SHA-1
}

// snapshotLocked copies e's visible state. The maps it shares are never
// mutated after they are stored, so the copy is safe to encode unlocked.
func (e *entry) snapshotLocked() Snapshot {
	s := Snapshot{
		ID:            e.id,
		State:         e.stateLocked(),
		Revision:      e.revision,
		Players:       e.players,
		Port:          e.port,
		Addresses:     e.addresses,
		Keys:          e.keys,
		ConfigVersion: e.configVersion,
		Config:        e.config,
		Hash:          e.configHash,
		Slots:         make([]SlotSnapshot, len(e.slots)),
	}
	for i, sl := range e.slots {
		ss := SlotSnapshot{Slot: i, Status: e.slotStatusLocked(sl), Tag: sl.tag}
		if r := sl.ready; r != nil && r.configVersion == e.configVersion {
			ss.Hash = r.hash
			ss.Missing = r.missing
		}
		s.Slots[i] = ss
	}
	return s
}

// CreateRequest is POST /game's body.
type CreateRequest struct {
	Players  int      `json:"players"`
	Password string   `json:"password"`
	Tag      string   `json:"tag"`
	Keys     KeyLists `json:"keys"`
}

// Created is POST /game's response. The host holds slot 0.
type Created struct {
	ID          string   `json:"id"`
	Password    string   `json:"password"`
	Players     int      `json:"players"`
	Port        string   `json:"port"`
	Addresses   []string `json:"addresses"`
	HostToken   string   `json:"host_token"`
	Slot        int      `json:"slot"`
	PlayerToken string   `json:"player_token"`
}

func validateKeys(k KeyLists) (map[string]bool, error) {
	if len(k.Sync) == 0 || len(k.Checksum) == 0 {
		return nil, invalid("keys.sync and keys.checksum are both required")
	}
	if len(k.Sync) > maxKeys || len(k.Checksum) > maxKeys {
		return nil, invalid("more than %d keys", maxKeys)
	}
	set := make(map[string]bool, len(k.Sync))
	for _, key := range k.Sync {
		if key == "" || len(key) > maxKeyLength {
			return nil, invalid("sync key %q is empty or longer than %d bytes", key, maxKeyLength)
		}
		set[key] = true
	}
	for _, key := range k.Checksum {
		if !set[key] {
			return nil, invalid("checksum key %q is not a sync key", key)
		}
	}
	return set, nil
}

// createSession reserves a game with a session, the host in slot 0. port
// and addresses are what players are told, decided by the HTTP layer.
func (l *Lobby) createSession(req CreateRequest, port string, addresses []string) (Created, error) {
	if len(req.Tag) > maxTagLength {
		return Created{}, invalid("tag longer than %d bytes", maxTagLength)
	}
	syncSet, err := validateKeys(req.Keys)
	if err != nil {
		return Created{}, err
	}

	l.mu.Lock()
	defer l.mu.Unlock()
	e, err := l.reserveLocked(req.Players, req.Password)
	if err != nil {
		return Created{}, err
	}
	e.port = port
	e.addresses = addresses
	e.hostToken = newToken()
	e.keys = req.Keys
	e.syncSet = syncSet
	e.slots[0] = slot{claimed: true, tag: req.Tag, token: newToken()}
	l.wg.Add(1)
	go l.reap(e)

	l.log.Info("session game created", "game", e.id, "players", e.players,
		"password_generated", req.Password == "", "sync_keys", len(req.Keys.Sync),
		"checksum_keys", len(req.Keys.Checksum), "games", len(l.byID))
	return Created{
		ID:          e.id,
		Password:    e.password,
		Players:     e.players,
		Port:        port,
		Addresses:   addresses,
		HostToken:   e.hostToken,
		Slot:        0,
		PlayerToken: e.slots[0].token,
	}, nil
}

// sessionLocked looks up a live game by id and restarts its idle wait. l.mu must
// be held.
func (l *Lobby) sessionLocked(id string) (*entry, error) {
	e := l.byID[id]
	if e == nil {
		return nil, errNotFound
	}
	e.touch()
	return e, nil
}

// joinSession claims the lowest free slot.
func (l *Lobby) joinSession(id, tag string) (slotIndex int, token string, err error) {
	if len(tag) > maxTagLength {
		return 0, "", invalid("tag longer than %d bytes", maxTagLength)
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	e, err := l.sessionLocked(id)
	if err != nil {
		return 0, "", err
	}
	if e.hostToken == "" || e.g != nil {
		return 0, "", errStarted
	}
	for i := range e.slots {
		if !e.slots[i].claimed {
			e.slots[i] = slot{claimed: true, tag: tag, token: newToken()}
			e.changedLocked()
			l.log.Info("player joined session", "game", e.id, "slot", i, "tag", tag)
			return i, e.slots[i].token, nil
		}
	}
	return 0, "", errSlotsFull
}

// leaveSession frees slot n, on its own token or the host's.
func (l *Lobby) leaveSession(id string, n int, token string) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	e, err := l.sessionLocked(id)
	if err != nil {
		return err
	}
	if n < 0 || n >= len(e.slots) || !e.slots[n].claimed {
		return errNoSuchSlot
	}
	if !tokenMatches(e.slots[n].token, token) && !e.isHostLocked(token) {
		return errForbidden
	}
	if n == 0 {
		return errHostSlot
	}
	if e.g != nil {
		return errStarted
	}
	e.slots[n] = slot{}
	e.changedLocked()
	l.log.Info("player left session", "game", e.id, "slot", n)
	return nil
}

// setConfig replaces the document, host only. The server-owned keys are
// written by the server; a host sending one is refused, as is any key
// outside the game's sync set or a document missing a checksum key.
func (l *Lobby) setConfig(id, token string, doc map[string]string) (version uint64, hash string, err error) {
	l.mu.Lock()
	defer l.mu.Unlock()
	e, err := l.sessionLocked(id)
	if err != nil {
		return 0, "", err
	}
	if !e.isHostLocked(token) {
		return 0, "", errForbidden
	}
	if e.g != nil {
		return 0, "", errStarted
	}
	if len(doc) > maxKeys {
		return 0, "", invalid("more than %d keys", maxKeys)
	}
	server := e.serverValues()
	config := make(map[string]string, len(doc)+len(server))
	for key, value := range doc {
		if _, owned := server[key]; owned {
			return 0, "", invalid("%s is set by the server", key)
		}
		if !e.syncSet[key] {
			return 0, "", invalid("%s is not one of this game's sync keys", key)
		}
		if len(value) > maxValueLength {
			return 0, "", invalid("value of %s is longer than %d bytes", key, maxValueLength)
		}
		config[key] = value
	}
	for key, value := range server {
		config[key] = value
	}
	hash, err = game.ConfigHash(e.keys.Checksum, config)
	if err != nil {
		return 0, "", invalid("%v", err)
	}

	e.config = config
	e.configVersion++
	e.configHash = hash
	for i := range e.slots {
		e.slots[i].ready = nil
	}
	e.changedLocked()
	l.log.Info("session config set", "game", e.id, "version", e.configVersion,
		"keys", len(config), "hash", hash)
	return e.configVersion, hash, nil
}

// ReadyRequest is the body of POST /game/{id}/players/{n}/ready: what one
// launcher got from applying a config version.
type ReadyRequest struct {
	ConfigVersion uint64            `json:"config_version"`
	Hash          string            `json:"hash"`
	Missing       map[string]string `json:"missing"`
}

// reportReady records slot n's result for the current config.
func (l *Lobby) reportReady(id string, n int, token string, req ReadyRequest) error {
	if len(req.Hash) > maxHashLength {
		return invalid("hash longer than %d bytes", maxHashLength)
	}
	if len(req.Missing) > maxKeys {
		return invalid("more than %d missing files", maxKeys)
	}
	for key, value := range req.Missing {
		if len(key) > maxKeyLength || len(value) > maxValueLength {
			return invalid("missing entry %q is too long", key)
		}
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	e, err := l.sessionLocked(id)
	if err != nil {
		return err
	}
	if n < 0 || n >= len(e.slots) || !e.slots[n].claimed {
		return errNoSuchSlot
	}
	if !tokenMatches(e.slots[n].token, token) {
		return errForbidden
	}
	if e.g != nil {
		return errStarted
	}
	if e.config == nil {
		return errNoConfig
	}
	if req.ConfigVersion != e.configVersion {
		return errStale
	}
	missing := req.Missing
	if len(missing) == 0 {
		missing = nil
	}
	e.slots[n].ready = &readyReport{configVersion: e.configVersion, hash: req.Hash, missing: missing}
	e.changedLocked()
	l.log.Info("session ready reported", "game", e.id, "slot", n,
		"status", e.slotStatusLocked(e.slots[n]), "missing", len(missing))
	return nil
}

// startSession routes the game and runs it, host only, once every slot is
// claimed and ready.
func (l *Lobby) startSession(id, token string) (Snapshot, error) {
	l.mu.Lock()
	defer l.mu.Unlock()
	e, err := l.sessionLocked(id)
	if err != nil {
		return Snapshot{}, err
	}
	if !e.isHostLocked(token) {
		return Snapshot{}, errForbidden
	}
	if e.g != nil {
		return Snapshot{}, errStarted
	}
	if e.stateLocked() != StateReady {
		return Snapshot{}, errNotReady
	}
	l.startLocked(e)
	l.log.Info("session game started", "game", e.id, "config_version", e.configVersion)
	return e.snapshotLocked(), nil
}

// endSession ends the game, host only.
func (l *Lobby) endSession(id, token string) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	e, err := l.sessionLocked(id)
	if err != nil {
		return err
	}
	if !e.isHostLocked(token) {
		return errForbidden
	}
	l.endLocked(e)
	l.log.Info("session game ended by host", "game", e.id)
	return nil
}
