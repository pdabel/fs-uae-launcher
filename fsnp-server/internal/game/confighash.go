package game

import (
	"crypto/sha1"
	"encoding/hex"
	"fmt"
)

// ConfigHash is the launcher's checksum_config: SHA-1 over the values of
// keys, in order, as UTF-8 with no separator. keys is the launcher's
// checksum key list, which depends on its Sync Config limits and lists
// some keys twice; both matter, so it is used as given, not sorted or
// deduplicated. A key missing from config is an error, as it is in the
// launcher, rather than a silent empty value.
//
// testdata/config-hash.json holds the golden cases; the launcher's
// test_checksum_golden.py checks checksum_config against the same file.
func ConfigHash(keys []string, config map[string]string) (string, error) {
	h := sha1.New()
	for _, key := range keys {
		value, ok := config[key]
		if !ok {
			return "", fmt.Errorf("config has no value for %q", key)
		}
		h.Write([]byte(value))
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}
