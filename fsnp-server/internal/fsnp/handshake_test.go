package fsnp

import (
	"os"
	"testing"
)

func readFixture(t *testing.T, name string) []byte {
	t.Helper()
	b, err := os.ReadFile("testdata/" + name)
	if err != nil {
		t.Fatalf("reading fixture %s: %v", name, err)
	}
	return b
}

// TestParseHandshake_Captured checks both real handshakes from the captured
// session in docs/netplay-fixtures/ (see that directory's README) round-trip
// through ParseHandshake with exactly the expected fields.
func TestParseHandshake_Captured(t *testing.T) {
	cases := []struct {
		file string
		tag  [3]byte
	}{
		{"client1-handshake.bin", [3]byte{'P', '1', 0}},
		{"client2-handshake.bin", [3]byte{'P', '2', 0}},
	}
	wantEmulatorVersion := [8]byte{'F', 'S', 'U', 'A', 'E', 3, 1, 66} // v3.1.66

	for _, c := range cases {
		raw := readFixture(t, c.file)
		h, err := ParseHandshake(raw)
		if err != nil {
			t.Fatalf("%s: ParseHandshake: %v", c.file, err)
		}
		if h.ProtocolVersion != ProtocolVersion {
			t.Errorf("%s: ProtocolVersion = %d, want %d", c.file, h.ProtocolVersion, ProtocolVersion)
		}
		if h.EmulatorVersion != wantEmulatorVersion {
			t.Errorf("%s: EmulatorVersion = %v, want %v (FSUAE 3.1.66)", c.file, h.EmulatorVersion, wantEmulatorVersion)
		}
		if h.SessionKey != 0 {
			t.Errorf("%s: SessionKey = %d, want 0 (first connect)", c.file, h.SessionKey)
		}
		if h.Player != NewPlayerByte {
			t.Errorf("%s: Player = %#x, want %#x (new player)", c.file, h.Player, NewPlayerByte)
		}
		if h.Tag != c.tag {
			t.Errorf("%s: Tag = %q, want %q", c.file, h.Tag, c.tag)
		}
		if h.ResumeFromPacket != 0 {
			t.Errorf("%s: ResumeFromPacket = %d, want 0", c.file, h.ResumeFromPacket)
		}

		// Round-trip: re-encoding the parsed struct must reproduce the
		// exact captured bytes.
		reencoded := h.Encode()
		if [HandshakeSize]byte(raw) != reencoded {
			t.Errorf("%s: Encode() did not round-trip: got % x, want % x", c.file, reencoded, raw)
		}
	}
}

func TestParseHandshake_PingProbe(t *testing.T) {
	// A bare PING probe (see connection_tester.py) is not a handshake.
	probe := []byte("PING000000000000000000000000")[:HandshakeSize]
	if !IsPingProbe(probe) {
		t.Fatal("IsPingProbe: expected true for PING-prefixed data")
	}
	if _, err := ParseHandshake(probe); err != ErrNotFSNP {
		t.Fatalf("ParseHandshake(PING probe) error = %v, want ErrNotFSNP", err)
	}
}

func TestParseHandshake_WrongSize(t *testing.T) {
	if _, err := ParseHandshake(make([]byte, 27)); err == nil {
		t.Fatal("expected error for undersized handshake")
	}
}
