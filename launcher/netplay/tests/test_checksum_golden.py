"""checksum_config against the golden cases fsnp-server checks too.

The fixture lives in the Go module's testdata, like the FSNP session
fixtures, so the server's game.ConfigHash test reads the same file. If
this fails, launchers and the server disagree on when configs match.
"""

import json
import os

import pytest

from launcher.launcher_config import LauncherConfig

FIXTURE = os.path.join(
    os.path.dirname(__file__),
    *[os.pardir] * 3,
    "fsnp-server",
    "internal",
    "game",
    "testdata",
    "config-hash.json",
)

with open(FIXTURE, encoding="UTF-8") as f:
    CASES = json.load(f)["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_checksum_config_matches_golden(case, monkeypatch):
    # The live key list depends on this machine's Sync Config, so hash
    # with the case's own list instead.
    monkeypatch.setattr(LauncherConfig, "checksum_keys", case["keys"])
    assert LauncherConfig.checksum_config(case["config"]) == case["sha1"]
