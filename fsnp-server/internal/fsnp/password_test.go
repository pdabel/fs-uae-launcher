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
