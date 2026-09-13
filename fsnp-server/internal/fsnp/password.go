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
