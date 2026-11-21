package lobby

import (
	"context"
	"errors"
	"io"
	"net/http"
	"sort"
	"time"
)

// maxTitleLength caps a game's display title.
const maxTitleLength = 64

// ListingRequest is POST /lobby's body. Since is 0 for an immediate answer;
// otherwise the call waits until the lobby's revision passes it.
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
		Games:    []ListedGame{},
	}
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
func (l *Lobby) waitListing(ctx context.Context, req ListingRequest, wait time.Duration) Listing {
	l.mu.Lock()
	defer l.mu.Unlock()
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
	return l.listingLocked()
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
	if req.Since != 0 {
		// The server's write timeout is shorter than the wait.
		_ = http.NewResponseController(w).SetWriteDeadline(time.Now().Add(longPollWait + httpWriteTimeout))
	}
	writeJSON(w, http.StatusOK, l.waitListing(r.Context(), req, longPollWait))
}
