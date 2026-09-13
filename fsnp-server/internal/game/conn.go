package game

import (
	"bufio"
	"crypto/subtle"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"net"
	"time"

	"github.com/pdabel/fs-uae-launcher/fsnp-server/internal/fsnp"
)

const (
	// HandshakeTimeout bounds how long a freshly accepted connection may take
	// to deliver its 28-byte handshake before it is dropped, so a half-open
	// socket can't hold a player slot (W9).
	HandshakeTimeout = 5 * time.Second

	// MaxTextLength caps an inbound MESSAGE_TEXT payload. The client only
	// displays 128 bytes; game.py accepted up to 16 MB (W9). The outbound
	// length field is 16-bit, so this also keeps the from_player bits intact.
	MaxTextLength = 1024

	// MaxSendChunk caps a single socket write. A word split across two TCP
	// segments trips client bug C1 in netplay.c's receive_thread; small
	// writes make that less likely. Mirrors game.py's MAX_SEND_CHUNK.
	MaxSendChunk = 1400

	// errorWriteTimeout bounds the direct write of a pre-join error word.
	errorWriteTimeout = 2 * time.Second

	// outQueueDepth is how many flushed buffers a writer may have pending
	// before the game goroutine treats the player as too slow and drops it.
	outQueueDepth = 64
)

// conn is one accepted socket. The reader runs in the goroutine that
// accepted it; the writer is started by the game goroutine when the join is
// accepted, and only the game goroutine ever sends on or closes out.
type conn struct {
	nc   net.Conn
	out  chan []byte
	addr string
}

func newConn(nc net.Conn) *conn {
	return &conn{
		nc:   nc,
		out:  make(chan []byte, outQueueDepth),
		addr: nc.RemoteAddr().String(),
	}
}

// HandleConn runs the handshake for one accepted connection, joins it to the
// game, and then reads messages from it until it fails. It blocks for the
// life of the connection; callers run it in its own goroutine.
func (g *Game) HandleConn(nc net.Conn) {
	if tc, ok := nc.(*net.TCPConn); ok {
		_ = tc.SetNoDelay(true)
	}
	c := newConn(nc)
	log := g.log.With("addr", c.addr)

	hs, err := c.readHandshake()
	if errors.Is(err, fsnp.ErrNotFSNP) {
		// Bare connectivity probe from connection_tester.py.
		_ = nc.SetWriteDeadline(time.Now().Add(errorWriteTimeout))
		_, _ = nc.Write(fsnp.PongResponse())
		_ = nc.Close()
		return
	}
	if err != nil {
		log.Warn("handshake failed", "err", err)
		_ = nc.Close()
		return
	}
	if hs.ProtocolVersion != fsnp.ProtocolVersion {
		log.Warn("protocol mismatch", "version", hs.ProtocolVersion)
		c.writeErrorAndClose(fsnp.ErrProtocolMismatch)
		return
	}
	var want, got [4]byte
	binary.BigEndian.PutUint32(want[:], g.cfg.PasswordHash)
	binary.BigEndian.PutUint32(got[:], hs.PasswordHash)
	if subtle.ConstantTimeCompare(want[:], got[:]) != 1 {
		log.Warn("wrong password")
		c.writeErrorAndClose(fsnp.ErrWrongPassword)
		return
	}

	reply := make(chan joinReply, 1)
	if !g.post(event{kind: evJoin, c: c, join: &joinRequest{hs: hs, reply: reply}}) {
		_ = nc.Close()
		return
	}
	var r joinReply
	select {
	case r = <-reply:
	case <-g.done:
		_ = nc.Close()
		return
	}
	if r.errCode != 0 {
		log.Warn("join rejected", "error", r.errCode)
		c.writeErrorAndClose(r.errCode)
		return
	}
	c.readLoop(g)
}

// readHandshake reads the leading 4 bytes and, unless they are the PING
// probe, the remaining 24 bytes of the handshake.
func (c *conn) readHandshake() (fsnp.Handshake, error) {
	_ = c.nc.SetReadDeadline(time.Now().Add(HandshakeTimeout))
	defer c.nc.SetReadDeadline(time.Time{})

	var buf [fsnp.HandshakeSize]byte
	if _, err := io.ReadFull(c.nc, buf[:4]); err != nil {
		return fsnp.Handshake{}, err
	}
	if fsnp.IsPingProbe(buf[:4]) {
		return fsnp.Handshake{}, fsnp.ErrNotFSNP
	}
	if _, err := io.ReadFull(c.nc, buf[4:]); err != nil {
		return fsnp.Handshake{}, err
	}
	return fsnp.ParseHandshake(buf[:])
}

// writeErrorAndClose sends one MESSAGE_ERROR word directly (there is no
// writer goroutine before a join succeeds) and closes the socket.
func (c *conn) writeErrorAndClose(code byte) {
	w := fsnp.NewExtMessage(fsnp.CmdError, uint32(code)).Encode()
	_ = c.nc.SetWriteDeadline(time.Now().Add(errorWriteTimeout))
	_, _ = c.nc.Write(w[:])
	_ = c.nc.Close()
}

// readLoop decodes 4-byte words from the socket and posts them to the game
// goroutine until the socket fails, then reports the connection gone. It
// never touches game state directly.
func (c *conn) readLoop(g *Game) {
	br := bufio.NewReaderSize(c.nc, 4096)
	var word [4]byte
	for {
		if _, err := io.ReadFull(br, word[:]); err != nil {
			g.post(event{kind: evGone, c: c, err: err})
			return
		}
		m := fsnp.DecodeMessage(word[:])
		switch {
		case m.IsExt():
			switch m.Command() {
			case fsnp.CmdMemCheck:
				g.post(event{kind: evMemCheck, c: c, data: m.Data()})
			case fsnp.CmdRndCheck:
				g.post(event{kind: evRndCheck, c: c, data: m.Data()})
			case fsnp.CmdPing:
				g.post(event{kind: evPong, c: c})
			case fsnp.CmdText:
				n := m.Data()
				if n > MaxTextLength {
					g.post(event{kind: evGone, c: c, err: fmt.Errorf("text message of %d bytes exceeds %d", n, MaxTextLength)})
					_ = c.nc.Close()
					return
				}
				text := make([]byte, n)
				if _, err := io.ReadFull(br, text); err != nil {
					g.post(event{kind: evGone, c: c, err: err})
					return
				}
				g.post(event{kind: evText, c: c, text: text})
			default:
				// game.py silently ignores unknown extended commands.
				g.log.Debug("ignoring ext command", "addr", c.addr, "command", m.Command())
			}
		case m.IsFrame():
			g.post(event{kind: evAck, c: c, data: m.FrameNumber()})
		case m.IsInput():
			g.post(event{kind: evInput, c: c, data: m.InputEvent()})
		default:
			g.log.Warn("unknown message", "addr", c.addr, "word", fmt.Sprintf("%08x", uint32(m)))
		}
	}
}

// writeLoop writes each flushed buffer to the socket in chunks of at most
// MaxSendChunk bytes, then closes the socket when out is closed. On a write
// error it keeps draining out so the game goroutine's sends stay
// non-blocking; the closed socket makes the reader report the loss.
func (c *conn) writeLoop() {
	defer c.nc.Close()
	for buf := range c.out {
		for len(buf) > 0 {
			n := min(len(buf), MaxSendChunk)
			if _, err := c.nc.Write(buf[:n]); err != nil {
				// Close now so the reader fails and reports the loss; the
				// game goroutine then closes out and this drain finishes.
				_ = c.nc.Close()
				for range c.out {
				}
				return
			}
			buf = buf[n:]
		}
	}
}
