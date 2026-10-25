"""Server in lobby mode, as /hostgame runs it."""

import pytest

from launcher.netplay.lobby_client import LobbyClient
from launcher.server import Server as server_module
from launcher.server.Server import Server


@pytest.fixture
def server(fsnp_server_binary, monkeypatch):
    monkeypatch.setattr(
        server_module, "find_server_executable", lambda: fsnp_server_binary
    )
    monkeypatch.setattr(server_module, "log_file_path", lambda: None)
    servers = []

    def make(**kwargs):
        s = Server(0, 2, "", **kwargs)
        servers.append(s)
        return s

    yield make
    for s in servers:
        s.stop()


def test_lobby_tells_players_the_public_addresses(server):
    s = server(lobby=True, public_addresses="203.0.113.4,host.example")
    s.start()
    assert s.port != 0
    created = LobbyClient("127.0.0.1", s.port).create_game(
        2, "", "HST", ["amiga_model"], ["amiga_model"]
    )
    assert created["addresses"] == ["203.0.113.4", "host.example"]
    assert created["port"] == str(s.port)


def test_stop_ends_the_lobby(server):
    s = server(lobby=True)
    s.start()
    process = s.process
    s.stop()
    assert process.poll() is not None
