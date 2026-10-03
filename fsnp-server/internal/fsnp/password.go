package fsnp

import (
	"crypto/sha1"
	"encoding/binary"
)

// PasswordHash reproduces game.py's create_game_password / netplay.c's
// password digest: SHA-1("FSNP" + ascii-only(password)), first 4 bytes as a
// big-endian uint32. Non-ASCII bytes of password are dropped entirely — a
// Go string is already UTF-8 bytes, so filtering byte < 0x80 here is
// byte-for-byte equivalent to the Python implementation's post-UTF-8-encode
// filter.
func PasswordHash(password string) uint32 {
	h := sha1.New()
	h.Write([]byte("FSNP"))

	filtered := make([]byte, 0, len(password))
	for i := 0; i < len(password); i++ {
		if password[i] < 128 {
			filtered = append(filtered, password[i])
		}
	}
	h.Write(filtered)

	sum := h.Sum(nil)
	return binary.BigEndian.Uint32(sum[:4])
}

// ExpectedPasswordHash returns the 4-byte password value a client is
// expected to send for the given game password.
//
// An empty password is not hashed at all. The client's
// g_fs_emu_netplay_password is zero-initialised and only filled in when the
// netplay_password option is set (netplay.c:71 and :210) — and
// fs_config_get_const_string treats an empty value as unset (conf.c:88) — so
// a client with no password configured sends four zero bytes, not a digest.
// game.py matched this with its `game_password = 0` default, which it
// replaced only when a --password argument was present.
//
// This differs from game.py in one edge case, deliberately: `--password=`
// with an explicitly empty value made game.py expect sha1("FSNP"), which no
// client can send when its own password is empty, so such a server rejected
// every player. Here an empty password always means "no password".
//
// Note that sha1("FSNP") is still reachable, and still handled by hashing:
// a password made up entirely of non-ASCII characters filters down to no
// bytes at all, on both sides.
func ExpectedPasswordHash(password string) uint32 {
	if password == "" {
		return 0
	}
	return PasswordHash(password)
}
