from types import SimpleNamespace

from launcher.launcher_config import LauncherConfig
from launcher.launcher_settings import LauncherSettings
from launcher.launcherapp import LauncherApp

# What FS-UAE was told last time, left in a loaded config or custom options.
OLD = {
    "netplay_server": "old.example",
    "netplay_password": "old-password",
    "netplay_port": "25100",
}


def prepare(monkeypatch, config):
    monkeypatch.setattr(LauncherSettings, "items", lambda: {}.items())
    monkeypatch.setattr(LauncherConfig, "get_game_overrides", lambda: {})
    monkeypatch.setattr(
        "launcher.devicemanager.DeviceManager.get_devices_for_ports",
        lambda config: [SimpleNamespace(id="none") for _ in range(4)],
    )
    return LauncherApp.prepare_config(config)


def netplay_keys(prepared):
    return {key: prepared[key] for key in OLD}


def test_a_netplay_game_tells_fs_uae_only_its_own_server(monkeypatch):
    prepared = prepare(
        monkeypatch,
        {
            **OLD,
            "__netplay_game": "game-id",
            "__netplay_host": "203.0.113.5",
            "__netplay_password": "",
            "__netplay_port": "25101",
        },
    )
    assert netplay_keys(prepared) == {
        "netplay_server": "203.0.113.5",
        "netplay_password": "",
        "netplay_port": "25101",
    }


def test_outside_a_netplay_game_the_configs_own_keys_stay(monkeypatch):
    # Set by hand for FS-UAE's own netplay; the launcher isn't in a game.
    prepared = prepare(monkeypatch, dict(OLD))
    assert netplay_keys(prepared) == OLD
