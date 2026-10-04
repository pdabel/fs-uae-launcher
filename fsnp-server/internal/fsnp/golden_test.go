package fsnp

import "testing"

// TestDecode_ServerToClient_Startup checks the first few decoded words of a
// real server->client stream against what game.py is known to send right
// after a client's handshake: SESSION_KEY, then PLAYERS with
// (player<<8 | num_players).
func TestDecode_ServerToClient_Startup(t *testing.T) {
	raw := readFixture(t, "server-to-client1.bin")
	if len(raw)%4 != 0 {
		t.Fatalf("server-to-client1.bin length %d is not a multiple of 4", len(raw))
	}
	words := DecodeMessages(raw)
	if len(words) < 2 {
		t.Fatalf("expected at least 2 words, got %d", len(words))
	}

	if !words[0].IsExt() || words[0].Command() != CmdSessionKey {
		t.Fatalf("word[0] = %#08x, want an ext SESSION_KEY (cmd %d)", words[0], CmdSessionKey)
	}
	if !words[1].IsExt() || words[1].Command() != CmdPlayers {
		t.Fatalf("word[1] = %#08x, want an ext PLAYERS (cmd %d)", words[1], CmdPlayers)
	}
	// player 0 (this connection joined first), 2 players total.
	const wantPlayersData = 0<<8 | 2
	if d := words[1].Data(); d != wantPlayersData {
		t.Errorf("PLAYERS data = %#x, want %#x (player=0, count=2)", d, wantPlayersData)
	}
}

// TestTagBroadcastAsymmetry locks in a real, non-obvious quirk found by
// reading the captured session: because game.py's Client.initialize_client
// calls send_player_tags(self) using whatever clients have joined *so far*,
// and __game_loop separately re-broadcasts every tag to every client at
// game start, the number of times each client receives each PLAYER_TAG_n
// depends on join order. See "Verified against a captured session" in
// docs/netplay-go-server-design.md. A Go rewrite that "simplifies" tag
// broadcasting into one clean call per join will change this — this test
// exists so that change is a deliberate decision, not an accident.
func TestTagBroadcastAsymmetry(t *testing.T) {
	cases := []struct {
		file          string
		wantTag0Count int
		wantTag1Count int
	}{
		{"server-to-client1.bin", 2, 1}, // player 0 (joined first)
		{"server-to-client2.bin", 2, 2}, // player 1 (joined second)
	}
	for _, c := range cases {
		raw := readFixture(t, c.file)
		words := DecodeMessages(raw)
		var tag0, tag1 int
		for _, w := range words {
			if !w.IsExt() {
				continue
			}
			switch w.Command() {
			case CmdPlayerTag0:
				tag0++
			case CmdPlayerTag1:
				tag1++
			}
		}
		if tag0 != c.wantTag0Count {
			t.Errorf("%s: PLAYER_TAG_0 count = %d, want %d", c.file, tag0, c.wantTag0Count)
		}
		if tag1 != c.wantTag1Count {
			t.Errorf("%s: PLAYER_TAG_1 count = %d, want %d", c.file, tag1, c.wantTag1Count)
		}
	}
}

// attributedChecks walks a client->server stream and tags each MEM_CHECK /
// RND_CHECK with the previously-acked frame, matching the server's
// attribution rule: the client sends RND_CHECK, then MEM_CHECK, then the
// frame ack (see "Per-frame sequence" in the design doc), so a check for
// frame f arrives while the tracked frame is still f-1.
func attributedChecks(t *testing.T, file string) (mem, rnd map[int64]uint32) {
	t.Helper()
	raw := readFixture(t, file)
	words := DecodeMessages(raw)
	mem = make(map[int64]uint32)
	rnd = make(map[int64]uint32)
	currentFrame := int64(-1)
	for _, w := range words {
		switch {
		case w.IsExt() && w.Command() == CmdMemCheck:
			mem[currentFrame] = w.Data()
		case w.IsExt() && w.Command() == CmdRndCheck:
			rnd[currentFrame] = w.Data()
		case w.IsFrame():
			currentFrame = int64(w.FrameNumber())
		}
	}
	return mem, rnd
}

// TestSyncCheckInvariant reproduces, as an automated regression test, the
// manual cross-client comparison done against the captured session: once
// checks are attributed to the correct (previous) frame, both players'
// checksums must agree on every common frame. This is the exact invariant
// the server's desync check depends on — see manifest.json's
// cross_client_check for the numbers this test asserts against.
func TestSyncCheckInvariant(t *testing.T) {
	mem1, rnd1 := attributedChecks(t, "client1-to-server.bin")
	mem2, rnd2 := attributedChecks(t, "client2-to-server.bin")

	const wantCommonFrames = 6164

	commonMem := 0
	memMismatches := 0
	for f, v1 := range mem1 {
		v2, ok := mem2[f]
		if !ok {
			continue
		}
		commonMem++
		if v1 != v2 {
			memMismatches++
			t.Errorf("MEM_CHECK mismatch at frame %d: client1=%#x client2=%#x", f, v1, v2)
		}
	}
	if commonMem != wantCommonFrames {
		t.Errorf("common MEM_CHECK frames = %d, want %d", commonMem, wantCommonFrames)
	}

	commonRnd := 0
	rndMismatches := 0
	for f, v1 := range rnd1 {
		v2, ok := rnd2[f]
		if !ok {
			continue
		}
		commonRnd++
		if v1 != v2 {
			rndMismatches++
			t.Errorf("RND_CHECK mismatch at frame %d: client1=%#x client2=%#x", f, v1, v2)
		}
	}
	if commonRnd != wantCommonFrames {
		t.Errorf("common RND_CHECK frames = %d, want %d", commonRnd, wantCommonFrames)
	}

	if memMismatches != 0 || rndMismatches != 0 {
		t.Fatalf("got %d MEM_CHECK and %d RND_CHECK mismatches, want 0 (this session had no desync)",
			memMismatches, rndMismatches)
	}
}

// TestMessageRoundTrip checks the constructors and accessors agree with
// each other and with game.py's bit layout for all three message kinds.
func TestMessageRoundTrip(t *testing.T) {
	ext := NewExtMessage(CmdSessionKey, 0x123456)
	if !ext.IsExt() || ext.Command() != CmdSessionKey || ext.Data() != 0x123456 {
		t.Errorf("ext round-trip failed: %#08x", ext)
	}

	frame := NewFrameMessage(6168)
	if ext.IsExt() == frame.IsExt() && frame.IsExt() {
		t.Fatal("frame message misclassified as ext")
	}
	if !frame.IsFrame() || frame.FrameNumber() != 6168 {
		t.Errorf("frame round-trip failed: %#08x", frame)
	}

	input := NewInputMessage(0x101b8)
	if input.IsExt() || input.IsFrame() || !input.IsInput() || input.InputEvent() != 0x101b8 {
		t.Errorf("input round-trip failed: %#08x", input)
	}
}
