import os
from types import SimpleNamespace

import pytest

from fsgs.FSGSDirectories import FSGSDirectories
from fsgs.saves import SaveHandler
from launcher.netplay.netplay import Netplay


@pytest.fixture
def save_states(tmp_path, monkeypatch):
    monkeypatch.setattr(
        FSGSDirectories, "get_save_states_dir", lambda: str(tmp_path)
    )
    # The Net Play tab has been opened: its Netplay object lasts until
    # the launcher quits, whether or not a netplay game is running.
    monkeypatch.setattr(Netplay, "_current", object())
    return tmp_path


def state_dir(config):
    fsgc = SimpleNamespace(config=config)
    return SaveHandler(fsgc, "Turrican II (A500)")._get_state_dir()


def test_game_outside_netplay_keeps_its_own_state_dir(save_states):
    assert state_dir({}) == os.path.join(save_states, "Turrican II (A500)")


def test_netplay_game_gets_a_clean_state_dir(save_states):
    config = {"__netplay_game": "k3x9q2"}
    assert state_dir(config) == os.path.join(save_states, "Net Play (k3x9q2)")


def test_netplay_state_dir_name_overrides(save_states):
    config = {
        "__netplay_game": "k3x9q2",
        "__netplay_state_dir_name": "Friday League",
    }
    assert state_dir(config) == os.path.join(save_states, "Friday League")
