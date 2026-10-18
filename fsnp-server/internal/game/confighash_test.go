package game

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

// TestConfigHashGolden checks ConfigHash against the cases the launcher's
// checksum_config is tested on, so the two can't drift apart.
func TestConfigHashGolden(t *testing.T) {
	raw, err := os.ReadFile(filepath.Join("testdata", "config-hash.json"))
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Cases []struct {
			Name   string            `json:"name"`
			Keys   []string          `json:"keys"`
			Config map[string]string `json:"config"`
			SHA1   string            `json:"sha1"`
		} `json:"cases"`
	}
	if err := json.Unmarshal(raw, &fixture); err != nil {
		t.Fatal(err)
	}
	if len(fixture.Cases) == 0 {
		t.Fatal("no cases in fixture")
	}
	for _, c := range fixture.Cases {
		t.Run(c.Name, func(t *testing.T) {
			got, err := ConfigHash(c.Keys, c.Config)
			if err != nil {
				t.Fatal(err)
			}
			if got != c.SHA1 {
				t.Errorf("got %s, want %s", got, c.SHA1)
			}
		})
	}
}

func TestConfigHashMissingKey(t *testing.T) {
	_, err := ConfigHash([]string{"amiga_model"}, map[string]string{})
	if err == nil {
		t.Fatal("want an error for a key missing from config")
	}
}
