package fsnp

import (
	"encoding/binary"
	"errors"
)

// HandshakeSize is the fixed length of an FSNP handshake, following the
// magic "FSNP" (or "PING" for a bare connectivity probe).
const HandshakeSize = 28

var (
	magic     = [4]byte{'F', 'S', 'N', 'P'}
	pingProbe = [4]byte{'P', 'I', 'N', 'G'}
	pongReply = []byte("PONG")
)

// ErrNotFSNP is returned by ParseHandshake when the leading 4 bytes are
// "PING" (a bare connectivity probe, see connection_tester.py) rather than
// a full handshake.
var ErrNotFSNP = errors.New("fsnp: PING probe, not a handshake")

// ProtocolVersion is the only version this package speaks. A client sending
// any other value gets ERROR_PROTOCOL_MISMATCH.
const ProtocolVersion = 1

// NewPlayerByte marks a handshake as requesting a new player slot, as
// opposed to resuming an existing one.
const NewPlayerByte = 0xFF

// Handshake is the 28-byte payload a client sends immediately after
// connecting, laid out exactly as fs_emu_netplay_connect constructs it in
// netplay.c (lines 726-765 in v3.1.66) and game.py's Client.initialize_client
// parses it.
type Handshake struct {
	ProtocolVersion  byte
	PasswordHash     uint32
	EmulatorVersion  [8]byte // raw; only compared for equality between players
	SessionKey       uint32  // 24-bit
	Player           byte    // NewPlayerByte (0xFF) or the slot to resume
	Tag              [3]byte
	ResumeFromPacket uint32
}

// IsPingProbe reports whether b's first 4 bytes are the bare "PING"
// connectivity probe rather than an "FSNP" handshake.
func IsPingProbe(b []byte) bool {
	return len(b) >= 4 && [4]byte(b[:4]) == pingProbe
}

// PongResponse is the fixed reply to a PING probe.
func PongResponse() []byte { return pongReply }

// ParseHandshake decodes a 28-byte FSNP handshake.
func ParseHandshake(b []byte) (Handshake, error) {
	var h Handshake
	if len(b) != HandshakeSize {
		return h, errors.New("fsnp: handshake must be exactly 28 bytes")
	}
	if IsPingProbe(b) {
		return h, ErrNotFSNP
	}
	if [4]byte(b[0:4]) != magic {
		return h, errors.New("fsnp: missing FSNP magic")
	}
	h.ProtocolVersion = b[4]
	h.PasswordHash = binary.BigEndian.Uint32(b[5:9])
	copy(h.EmulatorVersion[:], b[9:17])
	h.SessionKey = uint32(b[17])<<16 | uint32(b[18])<<8 | uint32(b[19])
	h.Player = b[20]
	copy(h.Tag[:], b[21:24])
	h.ResumeFromPacket = binary.BigEndian.Uint32(b[24:28])
	return h, nil
}

// Encode returns the 28-byte wire representation of h.
func (h Handshake) Encode() [HandshakeSize]byte {
	var b [HandshakeSize]byte
	copy(b[0:4], magic[:])
	b[4] = h.ProtocolVersion
	binary.BigEndian.PutUint32(b[5:9], h.PasswordHash)
	copy(b[9:17], h.EmulatorVersion[:])
	b[17] = byte(h.SessionKey >> 16)
	b[18] = byte(h.SessionKey >> 8)
	b[19] = byte(h.SessionKey)
	b[20] = h.Player
	copy(b[21:24], h.Tag[:])
	binary.BigEndian.PutUint32(b[24:28], h.ResumeFromPacket)
	return b
}
