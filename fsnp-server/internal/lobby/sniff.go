package lobby

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"sync"
	"time"

	"github.com/pdabel/fs-uae-launcher/fsnp-server/internal/fsnp"
	"github.com/pdabel/fs-uae-launcher/fsnp-server/internal/game"
)

const (
	// httpShutdownTimeout bounds how long Serve waits for in-flight HTTP
	// requests once it is told to stop.
	httpShutdownTimeout = 5 * time.Second

	// errorWriteTimeout bounds the write of a routing error word.
	errorWriteTimeout = 2 * time.Second

	// httpMaxHeaderBytes caps request headers; /game/create needs a few
	// hundred bytes.
	httpMaxHeaderBytes = 8 << 10

	// maxAcceptBackoff caps the pause between retries after Accept fails.
	maxAcceptBackoff = time.Second
)

// HTTP connection limits. Every game shares the lobby's port and process, so
// a client that holds HTTP connections open — idle after a response, or
// promising a body it never sends — must not be able to pile them up until
// the process runs out of file descriptors. Variables so tests can shorten
// them.
var (
	httpReadTimeout  = 10 * time.Second // whole request, body included
	httpWriteTimeout = 10 * time.Second
	httpIdleTimeout  = 30 * time.Second // keep-alive between requests
)

// Serve accepts connections on ln until ctx is cancelled or Accept fails,
// dispatching each on its first four bytes: "FSNP" is routed to a game,
// "PING" gets "PONG", anything else is handed to the HTTP API. On return
// every game has been stopped and the HTTP server shut down; a lobby is not
// reusable after Serve.
func (l *Lobby) Serve(ctx context.Context, ln net.Listener) error {
	hl := newConnListener(ln.Addr())
	srv := &http.Server{
		Handler:           l.Handler(),
		ReadHeaderTimeout: game.HandshakeTimeout,
		ReadTimeout:       httpReadTimeout,
		WriteTimeout:      httpWriteTimeout,
		IdleTimeout:       httpIdleTimeout,
		MaxHeaderBytes:    httpMaxHeaderBytes,
	}
	httpDone := make(chan struct{})
	go func() {
		defer close(httpDone)
		_ = srv.Serve(hl)
	}()

	stop := make(chan struct{})
	go func() {
		select {
		case <-ctx.Done():
		case <-stop:
		}
		_ = ln.Close()
	}()

	// Accept errors other than the listener closing are retried with a
	// growing pause, as net/http does, rather than returned: returning
	// stops every game in the lobby, and the likeliest cause — running out
	// of file descriptors — clears as connections close.
	var acceptErr error
	var backoff time.Duration
	for {
		nc, err := ln.Accept()
		if err != nil {
			if ctx.Err() != nil {
				break
			}
			if errors.Is(err, net.ErrClosed) {
				acceptErr = err
				break
			}
			backoff = min(max(2*backoff, 5*time.Millisecond), maxAcceptBackoff)
			l.log.Warn("accept failed, retrying", "err", err, "retry_in", backoff)
			select {
			case <-time.After(backoff):
			case <-ctx.Done():
			}
			continue
		}
		backoff = 0
		go l.dispatch(nc, hl)
	}
	close(stop)

	l.log.Info("lobby stopping", "games", l.Len())
	l.shutdown()
	sctx, cancel := context.WithTimeout(context.Background(), httpShutdownTimeout)
	defer cancel()
	_ = srv.Shutdown(sctx)
	<-httpDone
	return acceptErr
}

// dispatch reads the first four bytes of nc and sends it on its way.
func (l *Lobby) dispatch(nc net.Conn, hl *connListener) {
	_ = nc.SetReadDeadline(time.Now().Add(game.HandshakeTimeout))
	var buf [fsnp.HandshakeSize]byte
	if _, err := io.ReadFull(nc, buf[:4]); err != nil {
		_ = nc.Close()
		return
	}
	switch {
	case fsnp.IsPingProbe(buf[:4]):
		// Bare connectivity probe from connection_tester.py.
		_ = nc.SetWriteDeadline(time.Now().Add(errorWriteTimeout))
		_, _ = nc.Write(fsnp.PongResponse())
		_ = nc.Close()
	case string(buf[:4]) == "FSNP":
		l.route(nc, buf)
	default:
		// http.Server sets its own deadlines from here on.
		_ = nc.SetReadDeadline(time.Time{})
		if !hl.deliver(&prefixConn{Conn: nc, r: io.MultiReader(bytes.NewReader(append([]byte(nil), buf[:4]...)), nc)}) {
			_ = nc.Close()
		}
	}
}

// route reads the rest of an FSNP handshake and hands the connection to the
// game its password hash names. The version is checked first, as a single
// game does, because a client speaking another protocol can't be trusted to
// have put a hash where v1 expects one.
func (l *Lobby) route(nc net.Conn, buf [fsnp.HandshakeSize]byte) {
	log := l.log.With("addr", nc.RemoteAddr().String())
	if _, err := io.ReadFull(nc, buf[4:]); err != nil {
		log.Warn("handshake failed", "err", err)
		_ = nc.Close()
		return
	}
	_ = nc.SetReadDeadline(time.Time{})
	hs, err := fsnp.ParseHandshake(buf[:])
	if err != nil {
		log.Warn("handshake failed", "err", err)
		_ = nc.Close()
		return
	}
	if hs.ProtocolVersion != fsnp.ProtocolVersion {
		log.Warn("protocol mismatch", "version", hs.ProtocolVersion)
		writeErrorAndClose(nc, fsnp.ErrProtocolMismatch)
		return
	}
	g := l.lookup(hs.PasswordHash)
	if g == nil {
		// Either a wrong password or a game that has already ended; the
		// hash is all there is to go on, so it can't say which game the
		// player meant.
		log.Warn("no game for password",
			"received", hashString(hs.PasswordHash),
			"client_sent_password", hs.PasswordHash != 0)
		writeErrorAndClose(nc, fsnp.ErrWrongPassword)
		return
	}
	g.HandleJoin(nc, hs)
}

func hashString(h uint32) string { return fmt.Sprintf("%08x", h) }

func writeErrorAndClose(nc net.Conn, code byte) {
	w := fsnp.NewExtMessage(fsnp.CmdError, uint32(code)).Encode()
	_ = nc.SetWriteDeadline(time.Now().Add(errorWriteTimeout))
	_, _ = nc.Write(w[:])
	_ = nc.Close()
}

// prefixConn replays the bytes the sniffer already consumed.
type prefixConn struct {
	net.Conn
	r io.Reader
}

func (c *prefixConn) Read(p []byte) (int, error) { return c.r.Read(p) }

// connListener is a net.Listener fed by the sniffer rather than a socket, so
// an http.Server can serve the connections it decides are HTTP.
type connListener struct {
	addr  net.Addr
	conns chan net.Conn
	done  chan struct{}
	once  sync.Once
}

func newConnListener(addr net.Addr) *connListener {
	return &connListener{addr: addr, conns: make(chan net.Conn), done: make(chan struct{})}
}

// deliver hands c to Accept, or reports false if the listener is closed.
func (l *connListener) deliver(c net.Conn) bool {
	select {
	case l.conns <- c:
		return true
	case <-l.done:
		return false
	}
}

func (l *connListener) Accept() (net.Conn, error) {
	select {
	case c := <-l.conns:
		return c, nil
	case <-l.done:
		return nil, net.ErrClosed
	}
}

func (l *connListener) Close() error {
	l.once.Do(func() { close(l.done) })
	return nil
}

func (l *connListener) Addr() net.Addr { return l.addr }
