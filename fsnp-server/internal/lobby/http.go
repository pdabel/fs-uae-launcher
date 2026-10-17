package lobby

import (
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"strconv"
	"strings"
)

// Handler returns the lobby's HTTP API:
//
//	GET /game/create?players=N&password=P
//	  → 200 text/plain  id=…&password=…&port=…&addresses=…
//	GET /healthz
//	  → 200 text/plain  ok
//
// /game/create's response is form-encoded because that is what /startgame
// in launcher/netplay/netplay.py parses (parse_qs). Every game is on the
// lobby's own port, so port is the one the client reached the lobby on.
func (l *Lobby) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /game/create", l.handleCreate)
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		fmt.Fprintln(w, "ok")
	})
	return mux
}

func (l *Lobby) handleCreate(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	players, err := strconv.Atoi(q.Get("players"))
	if err != nil {
		http.Error(w, "players must be a number", http.StatusBadRequest)
		return
	}
	info, err := l.Create(players, q.Get("password"))
	switch {
	case err == nil:
	case errors.Is(err, ErrPasswordInUse):
		http.Error(w, err.Error(), http.StatusConflict)
		return
	case errors.Is(err, ErrFull), errors.Is(err, ErrClosed):
		http.Error(w, err.Error(), http.StatusServiceUnavailable)
		return
	default:
		// ErrPasswordLength, or game.New refusing the player count.
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	host, port := hostAndPort(r)
	addresses := l.cfg.PublicAddresses
	if len(addresses) == 0 {
		addresses = []string{host}
	}
	v := url.Values{}
	v.Set("id", info.ID)
	v.Set("password", info.Password)
	v.Set("port", port)
	v.Set("addresses", strings.Join(addresses, ","))
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	fmt.Fprint(w, v.Encode())
}

// hostAndPort is the address the client used to reach the lobby: the Host
// header, which carries the port as the client sees it (so a NAT or Docker
// port mapping is reported correctly), falling back to the listener's own
// port when the header has none.
func hostAndPort(r *http.Request) (string, string) {
	host, port, err := net.SplitHostPort(r.Host)
	if err != nil {
		host, port = r.Host, ""
	}
	if port == "" {
		if a, ok := r.Context().Value(http.LocalAddrContextKey).(net.Addr); ok {
			if _, p, err := net.SplitHostPort(a.String()); err == nil {
				port = p
			}
		}
	}
	return strings.Trim(host, "[]"), port
}
