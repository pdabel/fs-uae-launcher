package lobby

import (
	"fmt"
	"net/http"
	"strings"
	"testing"
	"time"
)

func (h *harness) listing(req ListingRequest) Listing {
	h.t.Helper()
	var l Listing
	h.mustCall(http.StatusOK, "POST", "/lobby", "", req, &l)
	return l
}

func (h *harness) newListedSession(players int, title string) Created {
	h.t.Helper()
	var c Created
	h.mustCall(http.StatusCreated, "POST", "/game", "", CreateRequest{
		Players: players, Tag: "HST", Keys: testKeys, Listed: true, Title: title,
	}, &c)
	return c
}

// pollListing starts a long-poll past since and returns its answer.
func (h *harness) pollListing(since uint64) <-chan Listing {
	got := make(chan Listing, 1)
	go func() {
		var l Listing
		h.call("POST", "/lobby", "", ListingRequest{Since: since}, &l)
		got <- l
	}()
	time.Sleep(50 * time.Millisecond)
	return got
}

func waitListing(t *testing.T, got <-chan Listing, what string) Listing {
	t.Helper()
	select {
	case l := <-got:
		return l
	case <-time.After(5 * time.Second):
		t.Fatalf("listing long-poll not woken by %s", what)
		return Listing{}
	}
}

func TestListing(t *testing.T) {
	h := startLobby(t, Config{Name: "Amiga Friday"})
	empty := h.listing(ListingRequest{})
	if empty.ID == "" || empty.Name != "Amiga Friday" || empty.Presence || empty.Games == nil || len(empty.Games) != 0 {
		t.Fatalf("empty listing %+v", empty)
	}

	c := h.newListedSession(2, "Sensible Soccer")
	h.newSession(2, "")      // unlisted: the default, as from an older launcher
	h.createOK(2, "classic") // /game/create games have no session to list
	l := h.listing(ListingRequest{})
	if l.ID != empty.ID {
		t.Fatalf("lobby id changed from %s to %s", empty.ID, l.ID)
	}
	if len(l.Games) != 1 {
		t.Fatalf("listed %d games, want only the listed one: %+v", len(l.Games), l.Games)
	}
	g := l.Games[0]
	if g.ID != c.ID || g.Title != "Sensible Soccer" || g.Host != "HST" || g.State != StateCreated ||
		g.Players != 2 || g.Joined != 1 || g.Created.IsZero() {
		t.Fatalf("listed game %+v", g)
	}

	if s := h.snapshot(c.ID); s.Title != "Sensible Soccer" || !s.Listed || s.AutoStart {
		t.Fatalf("snapshot title %q, listed %v, auto_start %v", s.Title, s.Listed, s.AutoStart)
	}
	h.joinSession(c.ID, "PL2")
	if g := h.listing(ListingRequest{}).Games[0]; g.Joined != 2 {
		t.Fatalf("joined %d after a join, want 2", g.Joined)
	}
}

// TestListingLongPoll checks that a listing poll is woken by every change
// a browser shows: create, join, leave, state, end, reaping — and not by
// an unlisted game.
func TestListingLongPoll(t *testing.T) {
	saved := longPollWait
	longPollWait = 300 * time.Millisecond
	t.Cleanup(func() { longPollWait = saved })

	clock := stillClock{after: make(chan time.Time)}
	h := startLobby(t, Config{Clock: clock})
	rev := h.listing(ListingRequest{}).Revision

	got := h.pollListing(rev)
	c := h.newListedSession(2, "Speedball 2")
	l := waitListing(t, got, "a create")
	if l.Revision <= rev || len(l.Games) != 1 {
		t.Fatalf("woke with revision %d (was %d), games %+v", l.Revision, rev, l.Games)
	}

	got = h.pollListing(l.Revision)
	j := h.joinSession(c.ID, "PL2")
	l = waitListing(t, got, "a join")
	if l.Games[0].Joined != 2 {
		t.Fatalf("joined %d, want 2", l.Games[0].Joined)
	}

	got = h.pollListing(l.Revision)
	h.mustCall(http.StatusNoContent, "DELETE", "/game/"+c.ID+"/players/1", j.PlayerToken, nil, nil)
	l = waitListing(t, got, "a leave")
	if l.Games[0].Joined != 1 {
		t.Fatalf("joined %d, want 1", l.Games[0].Joined)
	}

	got = h.pollListing(l.Revision)
	h.putConfig(c, testConfig)
	l = waitListing(t, got, "a config")
	if l.Games[0].State != StateConfiguring {
		t.Fatalf("state %q, want configuring", l.Games[0].State)
	}

	got = h.pollListing(l.Revision)
	h.mustCall(http.StatusNoContent, "DELETE", "/game/"+c.ID, c.HostToken, nil, nil)
	l = waitListing(t, got, "an end")
	if len(l.Games) != 0 {
		t.Fatalf("ended game still listed: %+v", l.Games)
	}

	// An unlisted game doesn't wake a listing poll: it answers at the
	// deadline, unchanged.
	rev = l.Revision
	start := time.Now()
	got = h.pollListing(rev)
	h.newSession(2, "")
	l = waitListing(t, got, "the deadline")
	if l.Revision != rev || time.Since(start) < longPollWait {
		t.Fatalf("unlisted create: revision %d (was %d) after %v", l.Revision, rev, time.Since(start))
	}

	// Reaped before start.
	h.newListedSession(2, "Turrican II")
	rev = h.listing(ListingRequest{}).Revision
	got = h.pollListing(rev)
	close(clock.after)
	l = waitListing(t, got, "reaping")
	if len(l.Games) != 0 {
		t.Fatalf("reaped game still listed: %+v", l.Games)
	}
}

func TestListingShowsRunningGames(t *testing.T) {
	h := startLobby(t, Config{})
	c := h.newListedSession(1, "Solo")
	set := h.putConfig(c, testConfig)
	h.ready(c.ID, 0, c.PlayerToken, ReadyRequest{ConfigVersion: set.ConfigVersion, Hash: set.Hash})
	wantState(t, h.snapshot(c.ID), StateReady)
	h.mustCall(http.StatusOK, "POST", "/game/"+c.ID+"/start", c.HostToken, nil, nil)
	if g := h.listing(ListingRequest{}).Games; len(g) != 1 || g[0].State != StateRunning {
		t.Fatalf("running game listed as %+v", g)
	}
}

func TestListingRequests(t *testing.T) {
	h := startLobby(t, Config{})
	// An empty body is an immediate answer, so the route can be tried by hand.
	req, _ := http.NewRequest("POST", "http://"+h.addr+"/lobby", nil)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("empty body: %d, want 200", resp.StatusCode)
	}
	if st := h.call("POST", "/lobby", "", map[string]any{"sinse": 3}, nil); st != http.StatusBadRequest {
		t.Fatalf("misspelt field: %d, want 400", st)
	}
	if st := h.call("GET", "/lobby", "", nil, nil); st != http.StatusMethodNotAllowed {
		t.Fatalf("GET /lobby: %d, want 405", st)
	}
	long := CreateRequest{Players: 2, Tag: "HST", Keys: testKeys, Listed: true, Title: strings.Repeat("x", maxTitleLength+1)}
	if st := h.call("POST", "/game", "", long, nil); st != http.StatusBadRequest {
		t.Fatalf("title too long: %d, want 400", st)
	}
}

func TestPresence(t *testing.T) {
	saved := longPollWait
	longPollWait = 300 * time.Millisecond
	t.Cleanup(func() { longPollWait = saved })

	h := startLobby(t, Config{Presence: true, PresenceTimeout: 200 * time.Millisecond})
	l := h.listing(ListingRequest{Member: "m-dave", Name: "Dave"})
	if !l.Presence || len(l.Online) != 1 || l.Online[0] != "Dave" {
		t.Fatalf("first member: presence %v, online %v", l.Presence, l.Online)
	}

	// Sam coming online wakes Dave's poll.
	got := make(chan Listing, 1)
	go func() {
		var l2 Listing
		h.call("POST", "/lobby", "", ListingRequest{Member: "m-dave", Name: "Dave", Since: l.Revision}, &l2)
		got <- l2
	}()
	time.Sleep(50 * time.Millisecond)
	h.listing(ListingRequest{Member: "m-sam", Name: "Sam"})
	l = waitListing(t, got, "a member coming online")
	if strings.Join(l.Online, ",") != "Dave,Sam" {
		t.Fatalf("online %v, want Dave,Sam", l.Online)
	}

	// Two launchers with one name stay separate; a nameless caller with
	// no member isn't counted.
	h.listing(ListingRequest{Member: "m-sam-2", Name: "Sam"})
	h.listing(ListingRequest{})
	if l = h.listing(ListingRequest{}); strings.Join(l.Online, ",") != "Dave,Sam,Sam" {
		t.Fatalf("online %v, want Dave,Sam,Sam", l.Online)
	}

	// Dave keeps a poll open; the others go quiet and expire, which wakes
	// Dave's poll.
	rev := l.Revision
	got = make(chan Listing, 1)
	go func() {
		for {
			var l2 Listing
			h.call("POST", "/lobby", "", ListingRequest{Member: "m-dave", Name: "Dave", Since: rev}, &l2)
			if l2.Revision > rev && len(l2.Online) == 1 {
				got <- l2
				return
			}
			rev = l2.Revision
		}
	}()
	l = waitListing(t, got, "members expiring")
	if l.Online[0] != "Dave" {
		t.Fatalf("online %v, want only Dave, who is polling", l.Online)
	}
}

func TestPresenceOff(t *testing.T) {
	h := startLobby(t, Config{})
	l := h.listing(ListingRequest{Member: "m-dave", Name: "Dave"})
	if l.Presence || l.Online != nil {
		t.Fatalf("presence off: presence %v, online %v", l.Presence, l.Online)
	}
	var raw map[string]any
	h.mustCall(http.StatusOK, "POST", "/lobby", "", ListingRequest{Member: "m-dave", Name: "Dave"}, &raw)
	if _, ok := raw["online"]; ok {
		t.Fatalf("presence off: online sent as %v", raw["online"])
	}
}

func TestPresenceLimits(t *testing.T) {
	h := startLobby(t, Config{Presence: true})
	if st := h.call("POST", "/lobby", "", ListingRequest{Member: "m", Name: strings.Repeat("x", maxTagLength+1)}, nil); st != http.StatusBadRequest {
		t.Fatalf("long name: %d, want 400", st)
	}
	if st := h.call("POST", "/lobby", "", ListingRequest{Member: strings.Repeat("m", maxMemberLength+1)}, nil); st != http.StatusBadRequest {
		t.Fatalf("long member: %d, want 400", st)
	}
	for i := range MaxMembers {
		h.listing(ListingRequest{Member: fmt.Sprintf("m-%d", i), Name: "P"})
	}
	if st := h.call("POST", "/lobby", "", ListingRequest{Member: "one-too-many", Name: "P"}, nil); st != http.StatusServiceUnavailable {
		t.Fatalf("member past the cap: %d, want 503", st)
	}
	// A member already counted still gets through, as does a caller with
	// no member.
	h.listing(ListingRequest{Member: "m-0", Name: "P"})
	h.listing(ListingRequest{})
}
