// Package fsnp implements the FSNP netplay wire protocol as spoken by
// FS-UAE v3.1.66 (libfsemu/src/emu/netplay.c) and launcher/server/game.py.
// Command numbers here match that pairing, not the renumbering introduced
// on fs-uae master in fd6fa3656 — see docs/netplay-go-server-design.md.
package fsnp

import "encoding/binary"

// Message is one 32-bit big-endian protocol word.
type Message uint32

const (
	extBit   = 1 << 31
	frameBit = 1 << 30
	inputBit = 1 << 29

	extCommandMask = 0x7F000000
	extDataMask    = 0x00FFFFFF
	frameMask      = 0x3FFFFFFF
	inputDataMask  = 0x00FFFFFF
)

// Extended command numbers (v3.1.66 / game.py numbering).
const (
	CmdReady            = 0
	CmdMemCheck         = 5
	CmdRndCheck         = 6
	CmdPing             = 7
	CmdPlayers          = 8
	CmdPlayerTag0       = 9
	CmdPlayerTag1       = 10
	CmdPlayerTag2       = 11
	CmdPlayerTag3       = 12
	CmdPlayerTag4       = 13
	CmdPlayerTag5       = 14
	CmdPlayerPing       = 15
	CmdPlayerLag        = 16
	CmdSetPlayerTag     = 17
	CmdProtocolVersion  = 18
	CmdEmulationVersion = 19
	CmdError            = 20
	CmdText             = 21
	CmdSessionKey       = 22
	CmdHalt             = 23
)

// Error codes sent via MESSAGE_ERROR.
const (
	ErrProtocolMismatch   = 1
	ErrWrongPassword      = 2
	ErrCannotResume       = 3
	ErrGameAlreadyStarted = 4
	ErrPlayerNumber       = 5
	ErrEmulatorMismatch   = 6
	ErrClientError        = 7
	ErrMemoryDesync       = 8
	ErrRandomDesync       = 9
	ErrSessionKey         = 10
	ErrGameStopped        = 99
)

// IsExt reports whether m is an extended (command, data) message.
func (m Message) IsExt() bool { return uint32(m)&extBit != 0 }

// Command returns the 7-bit extended command. Only meaningful if IsExt.
func (m Message) Command() byte { return byte((uint32(m) & extCommandMask) >> 24) }

// Data returns the 24-bit extended payload. Only meaningful if IsExt.
func (m Message) Data() uint32 { return uint32(m) & extDataMask }

// IsFrame reports whether m is a frame-ack/tick message.
// Matches game.py's priority order: checked only once IsExt is false.
func (m Message) IsFrame() bool {
	return !m.IsExt() && uint32(m)&frameBit != 0
}

// FrameNumber returns the 30-bit frame number. Only meaningful if IsFrame.
func (m Message) FrameNumber() uint32 { return uint32(m) & frameMask }

// IsInput reports whether m is a broadcast input event.
func (m Message) IsInput() bool {
	return !m.IsExt() && !m.IsFrame() && uint32(m)&inputBit != 0
}

// InputEvent returns the 24-bit input payload. Only meaningful if IsInput.
func (m Message) InputEvent() uint32 { return uint32(m) & inputDataMask }

// NewExtMessage builds an extended message, matching game.py's
// create_ext_message(ext, data).
func NewExtMessage(cmd byte, data uint32) Message {
	return Message(extBit | uint32(cmd)<<24 | (data & extDataMask))
}

// NewFrameMessage builds a frame-ack/tick message for the given frame number.
func NewFrameMessage(frame uint32) Message {
	return Message(frameBit | (frame & frameMask))
}

// NewInputMessage builds a broadcast input-event message.
func NewInputMessage(event uint32) Message {
	return Message(inputBit | (event & inputDataMask))
}

// Encode returns the 4-byte big-endian wire representation of m.
func (m Message) Encode() [4]byte {
	var b [4]byte
	binary.BigEndian.PutUint32(b[:], uint32(m))
	return b
}

// DecodeMessage reads one 4-byte big-endian word.
func DecodeMessage(b []byte) Message {
	return Message(binary.BigEndian.Uint32(b))
}

// DecodeMessages decodes a stream of concatenated 4-byte words. It does not
// attempt to separate out MESSAGE_TEXT payloads that follow a TEXT command —
// callers walking a stream with TEXT messages need to consume the payload
// themselves before continuing.
func DecodeMessages(b []byte) []Message {
	n := len(b) / 4
	out := make([]Message, n)
	for i := 0; i < n; i++ {
		out[i] = DecodeMessage(b[i*4 : i*4+4])
	}
	return out
}
