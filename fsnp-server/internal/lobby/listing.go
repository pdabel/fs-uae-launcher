package lobby

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"sort"
	"strings"
	"time"
)

const (
	// maxTitleLength caps a game's display title.
	maxTitleLength = 64

	// maxMemberLength caps a member id, which a launcher makes at random
	// once per run.
	maxMemberLength = 64
)

// ListingRequest is POST /lobby's body. Since is 0 for an immediate answer;
// otherwise the call waits until the lobby's revision passes it. Member
// and Name are what presence shows; without it they are ignored.
type ListingRequest struct {
	Member string `json:"member"`
	Name   string `json:"name"`
	Since  uint64 `json:"since"`
}

// Listing is POST /lobby's response: what a launcher browsing this lobby
// sees. It carries no tokens, passwords, configs or addresses; joining
// still goes through POST /game/{id}/players.
type Listing struct {
	ID       string       `json:"id"`
	Name     string       `json:"name"`
	Revision uint64       `json:"revision"`
	Presence bool         `json:"presence"`
	Online   []string     `json:"online,omitempty"`
	Games    []ListedGame `json:"games"`
}

// ListedGame is one game in a Listing.
type ListedGame struct {
	ID      string    `json:"id"`
	Title   string    `json:"title"`
	Host    string    `json:"host"`
	State   State     `json:"state"`
	Players int       `json:"players"`
	Joined  int       `json:"joined"`
	Created time.Time `json:"created"`
}

// member is one launcher browsing the listing, for presence. It is online
// while it has a poll open, or had one answered in the last
// PresenceTimeout.
type member struct {
	name     string
	lastSeen time.Time
	polling  int
}

// listingChangedLocked records a change to the listing and wakes every
// long-poll on it. l.mu must be held.
func (l *Lobby) listingChangedLocked() {
	l.revision++
	close(l.changed)
	l.changed = make(chan struct{})
}

// listingLocked copies the listing. l.mu must be held.
func (l *Lobby) listingLocked() Listing {
	listing := Listing{
		ID:       l.id,
		Name:     l.cfg.Name,
		Revision: l.revision,
		Presence: l.cfg.Presence,
		Games:    []ListedGame{},
	}
	for _, m := range l.members {
		listing.Online = append(listing.Online, m.name)
	}
	sort.Slice(listing.Online, func(i, j int) bool {
		a, b := strings.ToLower(listing.Online[i]), strings.ToLower(listing.Online[j])
		if a != b {
			return a < b
		}
		return listing.Online[i] < listing.Online[j]
	})
	for _, e := range l.byID {
		if !e.listed || e.ended {
			continue
		}
		joined := 0
		for _, s := range e.slots {
			if s.claimed {
				joined++
			}
		}
		listing.Games = append(listing.Games, ListedGame{
			ID:      e.id,
			Title:   e.title,
			Host:    e.slots[0].tag,
			State:   e.stateLocked(),
			Players: e.players,
			Joined:  joined,
			Created: e.created,
		})
	}
	sort.Slice(listing.Games, func(i, j int) bool {
		a, b := listing.Games[i], listing.Games[j]
		if !a.Created.Equal(b.Created) {
			return a.Created.Before(b.Created)
		}
		return a.ID < b.ID
	})
	return listing
}

// waitListing returns the listing once its revision is past since, wait
// elapses or ctx is done — whichever is first. since 0 answers at once.
// With presence, req's member counts as online throughout.
func (l *Lobby) waitListing(ctx context.Context, req ListingRequest, wait time.Duration) (Listing, error) {
	l.mu.Lock()
	defer l.mu.Unlock()
	if m, err := l.arriveLocked(req); err != nil {
		return Listing{}, err
	} else if m != nil {
		defer func() {
			m.polling--
			m.lastSeen = l.cfg.Clock.Now()
		}()
	}
	deadline := time.Now().Add(wait)
	for l.revision <= req.Since && ctx.Err() == nil {
		remaining := time.Until(deadline)
		if remaining <= 0 {
			break
		}
		changed := l.changed
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
	return l.listingLocked(), nil
}

// arriveLocked marks req's member as polling and returns it, or nil when
// presence is off or the caller gave no member. A member new to the lobby,
// or one that changed its name, changes the listing. l.mu must be held.
func (l *Lobby) arriveLocked(req ListingRequest) (*member, error) {
	if !l.cfg.Presence || req.Member == "" {
		return nil, nil
	}
	m := l.members[req.Member]
	if m == nil {
		if len(l.members) >= MaxMembers {
			return nil, ErrTooManyMembers
		}
		m = &member{name: req.Name}
		l.members[req.Member] = m
		l.listingChangedLocked()
		l.log.Debug("member online", "name", req.Name, "members", len(l.members))
	} else if m.name != req.Name {
		m.name = req.Name
		l.listingChangedLocked()
	}
	m.polling++
	m.lastSeen = l.cfg.Clock.Now()
	return m, nil
}

// sweepPresence drops members that have gone quiet, until the lobby shuts
// down.
func (l *Lobby) sweepPresence() {
	defer l.wg.Done()
	ticker := l.cfg.Clock.NewTicker(l.cfg.PresenceTimeout / 5)
	defer ticker.Stop()
	for {
		select {
		case <-ticker.C():
		case <-l.ctx.Done():
			return
		}
		l.mu.Lock()
		now := l.cfg.Clock.Now()
		gone := 0
		for id, m := range l.members {
			if m.polling == 0 && now.Sub(m.lastSeen) >= l.cfg.PresenceTimeout {
				delete(l.members, id)
				gone++
			}
		}
		if gone > 0 {
			l.listingChangedLocked()
			l.log.Debug("members offline", "gone", gone, "members", len(l.members))
		}
		l.mu.Unlock()
	}
}

func (l *Lobby) handleListing(w http.ResponseWriter, r *http.Request) {
	var req ListingRequest
	// An empty body asks for the listing at once, so the route can be
	// tried by hand.
	dec := decoder(w, r)
	if err := dec.Decode(&req); err != nil && !errors.Is(err, io.EOF) {
		writeError(w, http.StatusBadRequest, "invalid JSON body: "+err.Error())
		return
	}
	if len(req.Member) > maxMemberLength {
		writeError(w, http.StatusBadRequest, fmt.Sprintf("member longer than %d bytes", maxMemberLength))
		return
	}
	if len(req.Name) > maxTagLength {
		writeError(w, http.StatusBadRequest, fmt.Sprintf("name longer than %d bytes", maxTagLength))
		return
	}
	if req.Since != 0 {
		// The server's write timeout is shorter than the wait.
		_ = http.NewResponseController(w).SetWriteDeadline(time.Now().Add(longPollWait + httpWriteTimeout))
	}
	listing, err := l.waitListing(r.Context(), req, longPollWait)
	if err != nil {
		writeSessionError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, listing)
}
