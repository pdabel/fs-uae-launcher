from types import SimpleNamespace

from launcher.game_overrides import GameOverrideStore
from launcher.launcherapp import LauncherApp
from launcher.launcher_config import LOCAL_DISPLAY_OPTIONS, LauncherConfig
from launcher.launcher_settings import LauncherSettings


def test_display_overrides_are_not_netplay_sync_keys():
    assert not LOCAL_DISPLAY_OPTIONS & LauncherConfig.sync_keys_set


def test_game_override_store_keeps_empty_and_sparse_values(tmp_path):
    store = GameOverrideStore(tmp_path / "overrides.sqlite")
    first = ("variant_uuid", "first")
    second = ("variant_uuid", "second")

    store.set(first, "monitor", "")
    store.set(first, "zoom", "120")
    store.set(second, "monitor", "display:second")

    assert store.get(first) == {"monitor": "", "zoom": "120"}
    assert store.get(second) == {"monitor": "display:second"}

    store.clear(first, "zoom")
    assert store.get(first) == {"monitor": ""}


def test_prepare_config_applies_sparse_overrides_after_global_settings(
    monkeypatch,
):
    monkeypatch.setattr(
        LauncherSettings,
        "items",
        lambda: {
            "monitor": "global-display",
            "video_sync": "1",
            "scale": "global-scale",
        }.items(),
    )
    monkeypatch.setattr(
        LauncherConfig,
        "get_game_overrides",
        lambda: {"monitor": "saved-display"},
    )
    monkeypatch.setattr(
        "launcher.devicemanager.DeviceManager.get_devices_for_ports",
        lambda config: [SimpleNamespace(id="none") for _ in range(4)],
    )

    prepared = LauncherApp.prepare_config({"monitor": "saved-display"})

    assert prepared["monitor"] == "saved-display"
    assert prepared["video_sync"] == "1"
    assert prepared["scale"] == "global-scale"


def test_cli_values_override_saved_game_values(monkeypatch):
    monkeypatch.setattr(
        LauncherSettings,
        "items",
        lambda: {"monitor": "global-display"}.items(),
    )
    monkeypatch.setattr(
        LauncherConfig,
        "get_game_overrides",
        lambda: {"monitor": "saved-display"},
    )
    monkeypatch.setattr(
        "launcher.devicemanager.DeviceManager.get_devices_for_ports",
        lambda config: [SimpleNamespace(id="none") for _ in range(4)],
    )

    prepared = LauncherApp.prepare_config({"monitor": "cli-display"})

    assert prepared["monitor"] == "cli-display"


def test_empty_game_override_suppresses_global_setting(monkeypatch):
    monkeypatch.setattr(
        LauncherSettings,
        "items",
        lambda: {"monitor": "global-display"}.items(),
    )
    monkeypatch.setattr(
        LauncherConfig, "get_game_overrides", lambda: {"monitor": ""}
    )
    monkeypatch.setattr(
        "launcher.devicemanager.DeviceManager.get_devices_for_ports",
        lambda config: [SimpleNamespace(id="none") for _ in range(4)],
    )

    prepared = LauncherApp.prepare_config({"monitor": ""})

    assert prepared["monitor"] == ""


def test_empty_game_override_does_not_override_cli_value(monkeypatch):
    monkeypatch.setattr(
        LauncherSettings,
        "items",
        lambda: {"monitor": "global-display"}.items(),
    )
    monkeypatch.setattr(
        LauncherConfig, "get_game_overrides", lambda: {"monitor": ""}
    )
    monkeypatch.setattr(
        "launcher.devicemanager.DeviceManager.get_devices_for_ports",
        lambda config: [SimpleNamespace(id="none") for _ in range(4)],
    )

    prepared = LauncherApp.prepare_config({"monitor": "cli-display"})

    assert prepared["monitor"] == "cli-display"


def test_empty_monitor_override_uses_system_default(monkeypatch):
    from fsgs.amiga.fsuae import FSUAE
    from fsgs.drivers.gamedriver import GameDriver

    settings = {
        "monitor": "global-display",
        "window_width": "960",
        "window_height": "540",
    }
    selected_monitors = []
    monkeypatch.setattr(LauncherConfig, "get", lambda key: "")
    monkeypatch.setattr(
        LauncherConfig, "get_game_overrides", lambda: {"monitor": ""}
    )
    monkeypatch.setattr(
        LauncherSettings, "get", lambda key: settings.get(key, "")
    )
    monkeypatch.setattr(
        GameDriver,
        "screen_rect_for_monitor",
        lambda monitor: selected_monitors.append(monitor)
        or (0, 0, 1920, 1080),
    )
    monkeypatch.setattr(
        GameDriver, "fsuae_monitor_for_monitor", lambda monitor: None
    )

    FSUAE.center_window([], {})

    assert selected_monitors == [""]
