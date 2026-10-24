package lobby

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"
)

// maxBodyBytes caps a session API request body. A full config is a few
// tens of kilobytes at most.
const maxBodyBytes = 256 << 10

// longPollWait is how long GET /game/{id}?since=N waits for a change before
// answering with the unchanged snapshot. A variable so tests can shorten it.
var longPollWait = 25 * time.Second

// The session API, JSON in and out; host-only and player calls carry their
// token as "Authorization: Bearer <token>":
//
//	POST   /game                         create; the host holds slot 0
//	GET    /game/{id}[?since=revision]   snapshot; long-polls past revision
//	POST   /game/{id}/players            claim a slot
//	DELETE /game/{id}/players/{n}        free a slot (its token or the host's)
//	PUT    /game/{id}/config             host: replace the config document
//	POST   /game/{id}/players/{n}/ready  slot n: what applying it produced
//	POST   /game/{id}/start              host: route and run the FSNP game
//	DELETE /game/{id}                    host: end it
//
// Errors are {"error": "..."} with a status: 400 invalid, 403 bad token,
// 404 no such game or slot, 409 wrong state for the call, 503 full or
// shutting down.
func (l *Lobby) sessionRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /game", l.handleSessionCreate)
	mux.HandleFunc("GET /game/{id}", l.handleSnapshot)
	mux.HandleFunc("POST /game/{id}/players", l.handleJoin)
	mux.HandleFunc("DELETE /game/{id}/players/{n}", l.handleLeave)
	mux.HandleFunc("PUT /game/{id}/config", l.handleConfig)
	mux.HandleFunc("POST /game/{id}/players/{n}/ready", l.handleReady)
	mux.HandleFunc("POST /game/{id}/start", l.handleStart)
	mux.HandleFunc("DELETE /game/{id}", l.handleEnd)
}

func (l *Lobby) handleSessionCreate(w http.ResponseWriter, r *http.Request) {
	var req CreateRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	host, port := hostAndPort(r)
	addresses := l.cfg.PublicAddresses
	if len(addresses) == 0 {
		addresses = []string{host}
	}
	created, err := l.createSession(req, port, addresses)
	if err != nil {
		writeSessionError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, created)
}

func (l *Lobby) handleSnapshot(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	var since uint64
	if s := r.URL.Query().Get("since"); s != "" {
		var err error
		if since, err = strconv.ParseUint(s, 10, 64); err != nil {
			writeError(w, http.StatusBadRequest, "since must be a revision number")
			return
		}
		// The server's write timeout is shorter than the wait.
		_ = http.NewResponseController(w).SetWriteDeadline(time.Now().Add(longPollWait + httpWriteTimeout))
	}
	snap, err := l.waitSnapshot(r.Context(), id, since, longPollWait)
	if err != nil {
		writeSessionError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, snap)
}

// waitSnapshot returns id's snapshot once its revision is past since, it
// ends, wait elapses or ctx is done — whichever is first. since 0 answers
// at once. A game that ends while being waited on is reported as ended;
// asked for afterwards, it is gone.
func (l *Lobby) waitSnapshot(ctx context.Context, id string, since uint64, wait time.Duration) (Snapshot, error) {
	l.mu.Lock()
	e, err := l.sessionLocked(id)
	if err != nil {
		l.mu.Unlock()
		return Snapshot{}, err
	}
	deadline := time.Now().Add(wait)
	for e.revision <= since && !e.ended && ctx.Err() == nil {
		remaining := time.Until(deadline)
		if remaining <= 0 {
			break
		}
		changed := e.changed
		l.mu.Unlock()
		timer := time.NewTimer(remaining)
		select {
		case <-changed:
		case <-timer.C:
		case <-ctx.Done():
		}
		timer.Stop()
		l.mu.Lock()
	}
	snap := e.snapshotLocked()
	l.mu.Unlock()
	return snap, nil
}

type joinRequest struct {
	Tag string `json:"tag"`
}

type joined struct {
	Slot        int    `json:"slot"`
	PlayerToken string `json:"player_token"`
}

func (l *Lobby) handleJoin(w http.ResponseWriter, r *http.Request) {
	var req joinRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	n, token, err := l.joinSession(r.PathValue("id"), req.Tag)
	if err != nil {
		writeSessionError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, joined{Slot: n, PlayerToken: token})
}

func (l *Lobby) handleLeave(w http.ResponseWriter, r *http.Request) {
	n, ok := slotParam(w, r)
	if !ok {
		return
	}
	if err := l.leaveSession(r.PathValue("id"), n, bearer(r)); err != nil {
		writeSessionError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

type configRequest struct {
	Config configDocument `json:"config"`
}

// configDocument is a config of string values. A plain map[string]string
// would take a JSON null as "", so a document could pass validation and be
// hashed with a value its host never sent.
type configDocument map[string]string

func (d *configDocument) UnmarshalJSON(data []byte) error {
	var raw map[string]*string
	if err := json.Unmarshal(data, &raw); err != nil {
		return err
	}
	if raw == nil {
		*d = nil
		return nil
	}
	doc := make(configDocument, len(raw))
	for key, value := range raw {
		if value == nil {
			return fmt.Errorf("value of %s is null", key)
		}
		doc[key] = *value
	}
	*d = doc
	return nil
}

type configSet struct {
	ConfigVersion uint64 `json:"config_version"`
	Hash          string `json:"hash"`
}

func (l *Lobby) handleConfig(w http.ResponseWriter, r *http.Request) {
	var req configRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	if req.Config == nil {
		writeError(w, http.StatusBadRequest, "config is required")
		return
	}
	version, hash, err := l.setConfig(r.PathValue("id"), bearer(r), req.Config)
	if err != nil {
		writeSessionError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, configSet{ConfigVersion: version, Hash: hash})
}

func (l *Lobby) handleReady(w http.ResponseWriter, r *http.Request) {
	n, ok := slotParam(w, r)
	if !ok {
		return
	}
	var req ReadyRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	if err := l.reportReady(r.PathValue("id"), n, bearer(r), req); err != nil {
		writeSessionError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (l *Lobby) handleStart(w http.ResponseWriter, r *http.Request) {
	snap, err := l.startSession(r.PathValue("id"), bearer(r))
	if err != nil {
		writeSessionError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, snap)
}

func (l *Lobby) handleEnd(w http.ResponseWriter, r *http.Request) {
	if err := l.endSession(r.PathValue("id"), bearer(r)); err != nil {
		writeSessionError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func bearer(r *http.Request) string {
	token, _ := strings.CutPrefix(r.Header.Get("Authorization"), "Bearer ")
	return token
}

func slotParam(w http.ResponseWriter, r *http.Request) (int, bool) {
	n, err := strconv.Atoi(r.PathValue("n"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "slot must be a number")
		return 0, false
	}
	return n, true
}

// decodeJSON reads one JSON object into v, refusing unknown fields so a
// misspelt key is an error rather than a silent default.
func decodeJSON(w http.ResponseWriter, r *http.Request, v any) bool {
	dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, maxBodyBytes))
	dec.DisallowUnknownFields()
	if err := dec.Decode(v); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body: "+err.Error())
		return false
	}
	return true
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

func writeSessionError(w http.ResponseWriter, err error) {
	var bad invalidError
	status := http.StatusInternalServerError
	switch {
	case errors.As(err, &bad), errors.Is(err, ErrPasswordLength), errors.Is(err, ErrPlayers):
		status = http.StatusBadRequest
	case errors.Is(err, errForbidden):
		status = http.StatusForbidden
	case errors.Is(err, errNotFound), errors.Is(err, errNoSuchSlot):
		status = http.StatusNotFound
	case errors.Is(err, errStarted), errors.Is(err, errSlotsFull), errors.Is(err, errNoConfig),
		errors.Is(err, errStale), errors.Is(err, errNotReady), errors.Is(err, errHostSlot),
		errors.Is(err, ErrPasswordInUse):
		status = http.StatusConflict
	case errors.Is(err, ErrFull), errors.Is(err, ErrClosed):
		status = http.StatusServiceUnavailable
	}
	writeError(w, status, err.Error())
}
