package lobby

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"strconv"
	"testing"
	"time"

	"github.com/pdabel/fs-uae-launcher/fsnp-server/internal/fsnp"
	"github.com/pdabel/fs-uae-launcher/fsnp-server/internal/game"
)

// testKeys is a small stand-in for the launcher's key lists: two host keys,
// a media key, and the server-owned keys the launcher also tags checksum.
var testKeys = KeyLists{
	Sync: []string{
		"amiga_model", "chip_memory", "x_floppy_drive_0_sha1", "__netplay_port",
		"__netplay_game", "__netplay_password", "__netplay_players", "__netplay_addresses",
	},
	Checksum: []string{
		"amiga_model", "chip_memory", "x_floppy_drive_0_sha1",
		"__netplay_game", "__netplay_password", "__netplay_players", "__netplay_addresses",
		"chip_memory", // listed twice, as build_cfg does for some keys
	},
}

var testConfig = map[string]string{
	"amiga_model":           "A500",
	"chip_memory":           "512",
	"x_floppy_drive_0_sha1": "3a5c1eb2d2b5a9ca2b4a6d0d5bc53ce1b5c41d72",
}

// call makes one session API request and decodes a JSON reply into out
// (unless out is nil), returning the status.
func (h *harness) call(method, path, token string, body, out any) int {
	h.t.Helper()
	var buf bytes.Buffer
	if body != nil {
		if err := json.NewEncoder(&buf).Encode(body); err != nil {
			h.t.Fatal(err)
		}
	}
	req, err := http.NewRequest(method, "http://"+h.addr+path, &buf)
	if err != nil {
		h.t.Fatal(err)
	}
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	resp, err := (&http.Client{Timeout: 10 * time.Second}).Do(req)
	if err != nil {
		h.t.Fatal(err)
	}
	defer resp.Body.Close()
	if out != nil && resp.StatusCode < 300 && resp.StatusCode != http.StatusNoContent {
		if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
			h.t.Fatalf("%s %s: decode: %v", method, path, err)
		}
	}
	return resp.StatusCode
}

func (h *harness) mustCall(want int, method, path, token string, body, out any) {
	h.t.Helper()
	if got := h.call(method, path, token, body, out); got != want {
		h.t.Fatalf("%s %s: status %d, want %d", method, path, got, want)
	}
}

func (h *harness) newSession(players int, password string) Created {
	h.t.Helper()
	var c Created
	h.mustCall(http.StatusCreated, "POST", "/game", "",
		CreateRequest{Players: players, Password: password, Tag: "HST", Keys: testKeys}, &c)
	return c
}

func (h *harness) snapshot(id string) Snapshot {
	h.t.Helper()
	var s Snapshot
	h.mustCall(http.StatusOK, "GET", "/game/"+id, "", nil, &s)
	return s
}

func (h *harness) joinSession(id, tag string) joined {
	h.t.Helper()
	var j joined
	h.mustCall(http.StatusCreated, "POST", "/game/"+id+"/players", "", joinRequest{Tag: tag}, &j)
	return j
}

func (h *harness) putConfig(c Created, doc map[string]string) configSet {
	h.t.Helper()
	var set configSet
	h.mustCall(http.StatusOK, "PUT", "/game/"+c.ID+"/config", c.HostToken, configRequest{Config: doc}, &set)
	return set
}

func (h *harness) ready(id string, slot int, token string, req ReadyRequest) int {
	h.t.Helper()
	return h.call("POST", fmt.Sprintf("/game/%s/players/%d/ready", id, slot), token, req, nil)
}

func wantState(t *testing.T, s Snapshot, want State) {
	t.Helper()
	if s.State != want {
		t.Fatalf("state %q, want %q", s.State, want)
	}
}

// TestSessionLifecycle walks a two-player game from create to frames:
// config, a mismatch, a missing file, both ready, start, FSNP.
func TestSessionLifecycle(t *testing.T) {
	h := startLobby(t, Config{})
	c := h.newSession(2, "secret")
	if c.Password != "secret" || c.Slot != 0 || c.HostToken == "" || c.PlayerToken == "" {
		t.Fatalf("unexpected create reply %+v", c)
	}
	s := h.snapshot(c.ID)
	wantState(t, s, StateCreated)
	if s.Slots[0].Status != SlotWaiting || s.Slots[0].Tag != "HST" || s.Slots[1].Status != SlotEmpty {
		t.Fatalf("slots %+v", s.Slots)
	}

	// Reserved but not routed: an emulator can't join before start.
	h.join("secret", "EMU").waitError(fsnp.ErrWrongPassword)

	set := h.putConfig(c, testConfig)
	s = h.snapshot(c.ID)
	wantState(t, s, StateConfiguring)
	_, port, _ := net.SplitHostPort(h.addr)
	for key, want := range map[string]string{
		"__netplay_game": c.ID, "__netplay_password": "secret", "__netplay_players": "2",
		"__netplay_port": port, "__netplay_addresses": "127.0.0.1", "amiga_model": "A500",
	} {
		if s.Config[key] != want {
			t.Errorf("config[%s] = %q, want %q", key, s.Config[key], want)
		}
	}
	want, err := game.ConfigHash(testKeys.Checksum, s.Config)
	if err != nil || set.Hash != want || s.Hash != want {
		t.Fatalf("hash %q / %q, want %q (%v)", set.Hash, s.Hash, want, err)
	}

	p := h.joinSession(c.ID, "PL2")
	if p.Slot != 1 {
		t.Fatalf("joined slot %d, want 1", p.Slot)
	}

	if st := h.ready(c.ID, 0, c.PlayerToken, ReadyRequest{ConfigVersion: set.ConfigVersion, Hash: set.Hash}); st != http.StatusNoContent {
		t.Fatalf("host ready: %d", st)
	}
	h.ready(c.ID, 1, p.PlayerToken, ReadyRequest{ConfigVersion: set.ConfigVersion, Hash: "different"})
	s = h.snapshot(c.ID)
	if s.Slots[0].Status != SlotReady || s.Slots[1].Status != SlotMismatch || s.Slots[1].Hash != "different" {
		t.Fatalf("slots %+v", s.Slots)
	}
	if st := h.call("POST", "/game/"+c.ID+"/start", c.HostToken, nil, nil); st != http.StatusConflict {
		t.Fatalf("start before ready: %d, want 409", st)
	}

	missing := map[string]string{"x_floppy_drive_0_sha1": testConfig["x_floppy_drive_0_sha1"]}
	h.ready(c.ID, 1, p.PlayerToken, ReadyRequest{ConfigVersion: set.ConfigVersion, Hash: "different", Missing: missing})
	s = h.snapshot(c.ID)
	if s.Slots[1].Status != SlotMissing || s.Slots[1].Missing["x_floppy_drive_0_sha1"] == "" {
		t.Fatalf("slot 1 %+v, want missing with the file", s.Slots[1])
	}

	h.ready(c.ID, 1, p.PlayerToken, ReadyRequest{ConfigVersion: set.ConfigVersion, Hash: set.Hash})
	wantState(t, h.snapshot(c.ID), StateReady)

	if st := h.call("POST", "/game/"+c.ID+"/start", p.PlayerToken, nil, nil); st != http.StatusForbidden {
		t.Fatalf("start with a player token: %d, want 403", st)
	}
	var started Snapshot
	h.mustCall(http.StatusOK, "POST", "/game/"+c.ID+"/start", c.HostToken, nil, &started)
	wantState(t, started, StateRunning)

	e1, _ := h.joinOK("secret", "HST")
	e2, _ := h.joinOK("secret", "PL2")
	for _, e := range []*client{e1, e2} {
		if f := e.waitFrame(); f != 1 {
			t.Fatalf("first frame %d, want 1", f)
		}
	}
	if st := h.call("PUT", "/game/"+c.ID+"/config", c.HostToken, configRequest{Config: testConfig}, nil); st != http.StatusConflict {
		t.Fatalf("config after start: %d, want 409", st)
	}
}

func TestConfigChangeClearsReady(t *testing.T) {
	h := startLobby(t, Config{})
	c := h.newSession(1, "")
	v1 := h.putConfig(c, testConfig)
	h.ready(c.ID, 0, c.PlayerToken, ReadyRequest{ConfigVersion: v1.ConfigVersion, Hash: v1.Hash})
	wantState(t, h.snapshot(c.ID), StateReady)

	changed := map[string]string{"amiga_model": "A1200", "chip_memory": "2048", "x_floppy_drive_0_sha1": ""}
	v2 := h.putConfig(c, changed)
	if v2.ConfigVersion != v1.ConfigVersion+1 || v2.Hash == v1.Hash {
		t.Fatalf("v1 %+v, v2 %+v", v1, v2)
	}
	s := h.snapshot(c.ID)
	wantState(t, s, StateConfiguring)
	if s.Slots[0].Status != SlotWaiting {
		t.Fatalf("slot 0 %q, want waiting after a config change", s.Slots[0].Status)
	}
	if st := h.ready(c.ID, 0, c.PlayerToken, ReadyRequest{ConfigVersion: v1.ConfigVersion, Hash: v1.Hash}); st != http.StatusConflict {
		t.Fatalf("ready for a stale version: %d, want 409", st)
	}
}

func TestConfigValidation(t *testing.T) {
	h := startLobby(t, Config{})
	c := h.newSession(2, "")
	put := func(doc any, token string) int {
		return h.call("PUT", "/game/"+c.ID+"/config", token, map[string]any{"config": doc}, nil)
	}
	with := func(key, value string) map[string]string {
		doc := map[string]string{}
		for k, v := range testConfig {
			doc[k] = v
		}
		doc[key] = value
		return doc
	}
	withNull := func(key string) map[string]any {
		doc := map[string]any{}
		for k, v := range testConfig {
			doc[k] = v
		}
		doc[key] = nil
		return doc
	}
	for name, tc := range map[string]struct {
		doc   any
		token string
		want  int
	}{
		"player token":        {testConfig, c.PlayerToken, http.StatusForbidden},
		"no token":            {testConfig, "", http.StatusForbidden},
		"server-owned key":    {with("__netplay_password", "x"), c.HostToken, http.StatusBadRequest},
		"unknown key":         {with("floppy_drive_0", "/home/me/disk.adf"), c.HostToken, http.StatusBadRequest},
		"non-string value":    {map[string]any{"amiga_model": 500}, c.HostToken, http.StatusBadRequest},
		"null value":          {withNull("amiga_model"), c.HostToken, http.StatusBadRequest},
		"missing checksum":    {map[string]string{"amiga_model": "A500"}, c.HostToken, http.StatusBadRequest},
		"too long value":      {with("amiga_model", string(make([]byte, maxValueLength+1))), c.HostToken, http.StatusBadRequest},
		"valid, for contrast": {testConfig, c.HostToken, http.StatusOK},
	} {
		if got := put(tc.doc, tc.token); got != tc.want {
			t.Errorf("%s: status %d, want %d", name, got, tc.want)
		}
	}
	if st := h.call("PUT", "/game/"+c.ID+"/config", c.HostToken, map[string]any{"config": testConfig, "extra": 1}, nil); st != http.StatusBadRequest {
		t.Errorf("unknown field: status %d, want 400", st)
	}
	if st := h.call("PUT", "/game/nope/config", c.HostToken, configRequest{Config: testConfig}, nil); st != http.StatusNotFound {
		t.Errorf("unknown game: status %d, want 404", st)
	}
}

func TestCreateValidation(t *testing.T) {
	h := startLobby(t, Config{})
	for name, tc := range map[string]struct {
		req  CreateRequest
		want int
	}{
		"no keys":                  {CreateRequest{Players: 2}, http.StatusBadRequest},
		"checksum key not in sync": {CreateRequest{Players: 2, Keys: KeyLists{Sync: []string{"a"}, Checksum: []string{"b"}}}, http.StatusBadRequest},
		"too many players":         {CreateRequest{Players: 7, Keys: testKeys}, http.StatusBadRequest},
		"no players":               {CreateRequest{Players: 0, Keys: testKeys}, http.StatusBadRequest},
		"long tag":                 {CreateRequest{Players: 2, Tag: string(make([]byte, maxTagLength+1)), Keys: testKeys}, http.StatusBadRequest},
	} {
		if got := h.call("POST", "/game", "", tc.req, nil); got != tc.want {
			t.Errorf("%s: status %d, want %d", name, got, tc.want)
		}
	}

	// A reserved hash is taken for every kind of game, started or not.
	h.newSession(2, "taken")
	if st := h.call("POST", "/game", "", CreateRequest{Players: 2, Password: "taken", Keys: testKeys}, nil); st != http.StatusConflict {
		t.Errorf("second session with the same password: %d, want 409", st)
	}
	if st, _ := h.create("players=2&password=taken"); st != http.StatusConflict {
		t.Errorf("/game/create with a reserved password: %d, want 409", st)
	}
}

func TestSlots(t *testing.T) {
	h := startLobby(t, Config{})
	c := h.newSession(3, "")
	a := h.joinSession(c.ID, "AAA")
	b := h.joinSession(c.ID, "BBB")
	if a.Slot != 1 || b.Slot != 2 {
		t.Fatalf("slots %d, %d, want 1, 2", a.Slot, b.Slot)
	}
	if st := h.call("POST", "/game/"+c.ID+"/players", "", joinRequest{Tag: "CCC"}, nil); st != http.StatusConflict {
		t.Fatalf("join when full: %d, want 409", st)
	}

	leave := func(n int, token string) int {
		return h.call("DELETE", fmt.Sprintf("/game/%s/players/%d", c.ID, n), token, nil, nil)
	}
	if st := leave(1, b.PlayerToken); st != http.StatusForbidden {
		t.Fatalf("leave with another player's token: %d, want 403", st)
	}
	if st := leave(1, a.PlayerToken); st != http.StatusNoContent {
		t.Fatalf("leave: %d", st)
	}
	if st := leave(2, c.HostToken); st != http.StatusNoContent {
		t.Fatalf("host kick: %d", st)
	}
	if st := leave(0, c.HostToken); st != http.StatusConflict {
		t.Fatalf("host leaving slot 0: %d, want 409", st)
	}
	if st := leave(1, c.HostToken); st != http.StatusNotFound {
		t.Fatalf("leave an empty slot: %d, want 404", st)
	}
	if again := h.joinSession(c.ID, "DDD"); again.Slot != 1 {
		t.Fatalf("rejoin got slot %d, want the lowest free, 1", again.Slot)
	}
	if st := h.ready(c.ID, 1, a.PlayerToken, ReadyRequest{}); st != http.StatusForbidden {
		t.Fatalf("ready with a freed slot's old token: %d, want 403", st)
	}
}

// TestLongPoll checks that a poll past the current revision waits for a
// change, and that one with nothing to wait for answers at the deadline.
func TestLongPoll(t *testing.T) {
	saved := longPollWait
	longPollWait = 300 * time.Millisecond
	t.Cleanup(func() { longPollWait = saved })

	h := startLobby(t, Config{})
	c := h.newSession(2, "")
	rev := h.snapshot(c.ID).Revision

	got := make(chan Snapshot, 1)
	go func() {
		var s Snapshot
		h.call("GET", "/game/"+c.ID+"?since="+strconv.FormatUint(rev, 10), "", nil, &s)
		got <- s
	}()
	time.Sleep(50 * time.Millisecond)
	h.joinSession(c.ID, "PL2")
	select {
	case s := <-got:
		if s.Revision <= rev || s.Slots[1].Tag != "PL2" {
			t.Fatalf("woke with revision %d (was %d), slot 1 %+v", s.Revision, rev, s.Slots[1])
		}
	case <-time.After(5 * time.Second):
		t.Fatal("long poll not woken by a join")
	}

	rev = h.snapshot(c.ID).Revision
	start := time.Now()
	var s Snapshot
	h.mustCall(http.StatusOK, "GET", "/game/"+c.ID+"?since="+strconv.FormatUint(rev, 10), "", nil, &s)
	if s.Revision != rev || time.Since(start) < longPollWait {
		t.Fatalf("idle poll answered after %v with revision %d, want %v and %d", time.Since(start), s.Revision, longPollWait, rev)
	}
}

// TestEndWakesPollers ends a game while a launcher is waiting on it: the
// waiter sees "ended", and the game is gone afterwards.
func TestEndWakesPollers(t *testing.T) {
	h := startLobby(t, Config{})
	c := h.newSession(2, "")
	rev := h.snapshot(c.ID).Revision

	got := make(chan Snapshot, 1)
	go func() {
		var s Snapshot
		h.call("GET", "/game/"+c.ID+"?since="+strconv.FormatUint(rev, 10), "", nil, &s)
		got <- s
	}()
	time.Sleep(50 * time.Millisecond)
	if st := h.call("DELETE", "/game/"+c.ID, c.PlayerToken, nil, nil); st != http.StatusForbidden {
		t.Fatalf("end with a player token: %d, want 403", st)
	}
	h.mustCall(http.StatusNoContent, "DELETE", "/game/"+c.ID, c.HostToken, nil, nil)
	select {
	case s := <-got:
		wantState(t, s, StateEnded)
	case <-time.After(5 * time.Second):
		t.Fatal("long poll not woken by the end")
	}
	if st := h.call("GET", "/game/"+c.ID, "", nil, nil); st != http.StatusNotFound {
		t.Fatalf("ended game: %d, want 404", st)
	}
	h.waitLen(0)
}

func TestEndRunningGame(t *testing.T) {
	h := startLobby(t, Config{})
	c := h.newSession(1, "solo")
	set := h.putConfig(c, testConfig)
	h.ready(c.ID, 0, c.PlayerToken, ReadyRequest{ConfigVersion: set.ConfigVersion, Hash: set.Hash})
	h.mustCall(http.StatusOK, "POST", "/game/"+c.ID+"/start", c.HostToken, nil, nil)
	e, _ := h.joinOK("solo", "HST")
	e.waitFrame()

	h.mustCall(http.StatusNoContent, "DELETE", "/game/"+c.ID, c.HostToken, nil, nil)
	e.waitError(fsnp.ErrGameStopped)
	h.waitLen(0)
}

// TestIdleReap leaves a session game untouched: the reaper removes it and
// its password is free again.
func TestIdleReap(t *testing.T) {
	clock := stillClock{after: make(chan time.Time)}
	h := startLobby(t, Config{Clock: clock})
	c := h.newSession(2, "idle")

	close(clock.after)
	h.waitLen(0)
	if st := h.call("GET", "/game/"+c.ID, "", nil, nil); st != http.StatusNotFound {
		t.Fatalf("reaped game: %d, want 404", st)
	}
	if st, _ := h.create("players=2&password=idle"); st != http.StatusOK {
		t.Fatalf("password of a reaped game: %d, want it free", st)
	}
}

// waitingClock is a stillClock that reports each idle wait the reaper
// starts.
type waitingClock struct {
	stillClock
	waits chan struct{}
}

func (c waitingClock) After(d time.Duration) <-chan time.Time {
	select {
	case c.waits <- struct{}{}:
	default:
	}
	return c.stillClock.After(d)
}

// TestIdleReapSparesATouch runs the idle wait out just as a request
// touches the game: the reaper takes the timer, the touch lands while it
// waits for the lock, and the game must survive with the wait restarted.
func TestIdleReapSparesATouch(t *testing.T) {
	clock := waitingClock{stillClock{after: make(chan time.Time)}, make(chan struct{}, 8)}
	h := startLobby(t, Config{Clock: clock})
	c := h.newSession(2, "busy")
	<-clock.waits

	h.l.mu.Lock()
	clock.after <- time.Now()
	h.l.byID[c.ID].touch()
	h.l.mu.Unlock()

	select {
	case <-clock.waits:
	case <-time.After(5 * time.Second):
		t.Fatal("the reaper didn't restart its wait after a touch")
	}
	if n := h.l.Len(); n != 1 {
		t.Fatalf("%d games after a touched wait ran out, want 1", n)
	}
}

// TestCreateGameHasNoSession checks a /game/create game, which has no
// tokens, can't be driven over the session API, though it can be seen.
func TestCreateGameHasNoSession(t *testing.T) {
	h := startLobby(t, Config{})
	id := h.createOK(2, "legacy").Get("id")
	wantState(t, h.snapshot(id), StateRunning)
	if st := h.call("PUT", "/game/"+id+"/config", "", configRequest{Config: testConfig}, nil); st != http.StatusForbidden {
		t.Fatalf("config on a /game/create game: %d, want 403", st)
	}
	if st := h.call("POST", "/game/"+id+"/players", "", joinRequest{Tag: "X"}, nil); st != http.StatusConflict {
		t.Fatalf("join a /game/create game: %d, want 409", st)
	}
	if st := h.call("DELETE", "/game/"+id, "", nil, nil); st != http.StatusForbidden {
		t.Fatalf("end a /game/create game without a token: %d, want 403", st)
	}
}

// TestShutdownEndsSessions checks that pending session games don't hold up
// shutdown.
func TestShutdownEndsSessions(t *testing.T) {
	h := startLobby(t, Config{})
	h.newSession(2, "")
	h.newSession(3, "")
	if err := h.stop(); err != nil {
		t.Fatal(err)
	}
	if n := h.l.Len(); n != 0 {
		t.Fatalf("%d games left after shutdown", n)
	}
}
