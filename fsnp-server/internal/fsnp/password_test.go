package fsnp

import "testing"

// Expected values generated directly from launcher/server/game.py's
// create_game_password (see docs/netplay-go-server-design.md's "Fixtures
// don't need a captured session" section) — not from the pcap capture.
func TestPasswordHash(t *testing.T) {
	cases := []struct {
		password string
		want     uint32
	}{
		{"", 0x4baf510d},
		{"secret", 0xbd2ec2ea},
		{"héllo", 0x419d9eaf}, // non-ASCII bytes of 'é' must be dropped
	}
	for _, c := range cases {
		if got := PasswordHash(c.password); got != c.want {
			t.Errorf("PasswordHash(%q) = %#08x, want %#08x", c.password, got, c.want)
		}
	}
}

// TestExpectedPasswordHash covers the no-password case the client reaches by
// sending four zero bytes, which a plain SHA-1 of the empty string does not
// produce. See ExpectedPasswordHash for why.
func TestExpectedPasswordHash(t *testing.T) {
	if got := ExpectedPasswordHash(""); got != 0 {
		t.Errorf("ExpectedPasswordHash(\"\") = %#08x, want 0 (client sends zero bytes)", got)
	}
	for _, pw := range []string{"secret", "test", " ", "0"} {
		if got, want := ExpectedPasswordHash(pw), PasswordHash(pw); got != want {
			t.Errorf("ExpectedPasswordHash(%q) = %#08x, want %#08x", pw, got, want)
		}
	}
	// An all-non-ASCII password filters down to nothing on both sides, so it
	// hashes to sha1("FSNP") — which must not be confused with "no password".
	nonASCII := ExpectedPasswordHash("日本語")
	if nonASCII != PasswordHash("") {
		t.Errorf("ExpectedPasswordHash(non-ASCII) = %#08x, want %#08x", nonASCII, PasswordHash(""))
	}
	if nonASCII == 0 {
		t.Error("an all-non-ASCII password must not hash to 0, which means no password")
	}
}
