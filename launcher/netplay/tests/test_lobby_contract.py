"""LobbyClient against a real fsnp-server --lobby.

The unit tests pin what the client sends; this pins that the server
agrees. It needs the binary: FSNP_SERVER names one; otherwise it is built
with a local Go toolchain, falling back to fsnp-server/fsnp-server (what
`make -C fsnp-server` builds). With none of those it is skipped.
"""

import json
import os
import shutil
import subprocess
import threading

import pytest

from launcher.launcher_config import LauncherConfig
from launcher.netplay.lobby_client import (
    LobbyClient,
    LobbyError,
    SessionWatcher,
)

REPO = os.path.join(os.path.dirname(__file__), *[os.pardir] * 3)
MODULE = os.path.join(REPO, "fsnp-server")

SYNC = [
    "amiga_model",
    "chip_memory",
    "__netplay_game",
    "__netplay_password",
    "__netplay_players",
    "__netplay_port",
    "__netplay_addresses",
]
CHECKSUM = [
    "amiga_model",
    "chip_memory",
    "__netplay_game",
    "__netplay_password",
    "__netplay_players",
    "__netplay_addresses",
    "chip_memory",
]


def find_server(tmp_dir):
    if os.environ.get("FSNP_SERVER"):
        return os.environ["FSNP_SERVER"]
    # A fresh build when possible: a binary left over from an older make
    # may predate the API under test.
    go = shutil.which("go")
    if go is not None:
        out = os.path.join(tmp_dir, "fsnp-server")
        subprocess.run(
            [go, "build", "-o", out, "./cmd/fsnp-server"],
            cwd=MODULE,
            check=True,
            timeout=300,
        )
        return out
    built = os.path.join(MODULE, "fsnp-server")
    if os.path.isfile(built):
        return built
    return None


@pytest.fixture(scope="module")
def lobby(tmp_path_factory):
    binary = find_server(str(tmp_path_factory.mktemp("fsnp")))
    if binary is None:
        pytest.skip("no fsnp-server binary and no Go toolchain to build one")
    proc = subprocess.Popen(
        [binary, "--lobby", "--host", "127.0.0.1", "--port", "0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        ready = json.loads(proc.stdout.readline())
        assert ready["event"] == "listening", ready
        yield LobbyClient("127.0.0.1", ready["port"])
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_session_round_trip(lobby, monkeypatch):
    created = lobby.create_game(2, "", "HST", SYNC, CHECKSUM)
    game_id = created["id"]
    assert created["slot"] == 0

    snapshots = []
    changed = threading.Event()

    def on_snapshot(s):
        snapshots.append(s)
        changed.set()

    watcher = SessionWatcher(lobby, game_id, on_snapshot)
    watcher.start()

    reply = lobby.set_config(
        game_id,
        created["host_token"],
        {"amiga_model": "A500", "chip_memory": 512},
    )
    doc = lobby.game(game_id)
    assert doc["config_version"] == reply["config_version"]
    assert doc["config"]["__netplay_password"] == created["password"]
    assert doc["config"]["__netplay_players"] == "2"

    # The launcher's own hash, over the document's checksum list, is the
    # server's: what lets a player's ready match.
    monkeypatch.setattr(
        LauncherConfig, "checksum_keys", doc["keys"]["checksum"]
    )
    assert LauncherConfig.checksum_config(doc["config"]) == reply["hash"]

    player = lobby.join(game_id, "PL2")
    for slot, token in [
        (0, created["player_token"]),
        (player["slot"], player["player_token"]),
    ]:
        lobby.report_ready(
            game_id, slot, token, reply["config_version"], reply["hash"], {}
        )
    assert lobby.game(game_id)["state"] == "ready"

    with pytest.raises(LobbyError) as e:
        lobby.start(game_id, player["player_token"])
    assert e.value.status == 403
    assert lobby.start(game_id, created["host_token"])["state"] == "running"

    lobby.end(game_id, created["host_token"])
    watcher.join(timeout=10)
    assert not watcher.is_alive()
    assert snapshots[-1]["state"] == "ended"


def test_refused_config_names_the_key(lobby):
    created = lobby.create_game(1, "", "HST", SYNC, CHECKSUM)
    with pytest.raises(LobbyError) as e:
        lobby.set_config(
            created["id"],
            created["host_token"],
            {
                "amiga_model": "A500",
                "chip_memory": "512",
                "__netplay_port": "1",
            },
        )
    assert e.value.status == 400
    assert "__netplay_port" in e.value.message
    lobby.end(created["id"], created["host_token"])
