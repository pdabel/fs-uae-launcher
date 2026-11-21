from types import SimpleNamespace
import sqlite3
from unittest.mock import Mock

import pytest

from fsgs.Config import Config
from launcher.game_overrides import GameOverrideStore
from launcher.launcherapp import LauncherApp
from launcher.launcher_config import LOCAL_DISPLAY_OPTIONS, LauncherConfig
from launcher.launcher_settings import LauncherSettings


@pytest.fixture
def game_config(tmp_path, monkeypatch):
    import launcher.game_overrides as overrides
    import launcher.launcher_config as launcher_config

    signal = Mock()
    context = Mock()
    context.signal = signal
    config = Config(context)
    context.config = config
    config.values.update(
        {"monitor": "base-monitor", "__changed": "0", "__ready": "1"}
    )
    store = GameOverrideStore(tmp_path / "overrides.sqlite")
    settings = {"config_path": str(tmp_path / "game.fs-uae")}
    monkeypatch.setattr(launcher_config, "fsgs", context)
    monkeypatch.setattr(overrides, "game_override_store", store)
    monkeypatch.setattr(
        LauncherSettings, "get", lambda key: settings.get(key, "")
    )
    for key, value in (
        ("_game_base_identity", None),
        ("_game_base_values", {}),
        ("_game_override_values", {}),
        ("_game_overrides_available", False),
    ):
        monkeypatch.setattr(LauncherConfig, key, value)
    return context, store, settings


@pytest.mark.parametrize("override", ["other-monitor", ""])
def test_saved_config_preserves_base_and_override_edits_stay_clean(
    game_config, override
):
    context, store, _ = game_config
    LauncherConfig.apply_game_overrides()
    LauncherConfig.set_game_override("monitor", override)
    assert context.config.get("monitor") == override
    assert context.config.get("__changed") == "0"
    assert context.config.get("__ready") == "1"
    assert LauncherConfig.copy_for_save()["monitor"] == "base-monitor"

    LauncherConfig.clear_game_override("monitor")
    assert context.config.get("monitor") == "base-monitor"
    assert context.config.get("__changed") == "0"
    assert store.get(LauncherConfig.game_override_identity()) == {}


def test_override_edits_preserve_existing_dirty_state(game_config):
    context, _, _ = game_config
    context.config.values["__changed"] = "1"
    LauncherConfig.apply_game_overrides()
    LauncherConfig.set_game_override("monitor", "other-monitor")
    LauncherConfig.clear_game_override("monitor")
    assert context.config.get("__changed") == "1"


def test_actual_save_uses_base_values_with_unrelated_edits(
    game_config, tmp_path, monkeypatch
):
    from launcher.ui.savebutton import SaveButton

    context, _, settings = game_config
    settings["config_name"] = "Example"
    monkeypatch.setattr(LauncherSettings, "set", settings.__setitem__)
    monkeypatch.setattr(
        "launcher.ui.savebutton.FSGSDirectories.get_configurations_dir",
        lambda: str(tmp_path),
    )
    monkeypatch.setattr(
        "launcher.ui.savebutton.Database.get_instance", lambda: Mock()
    )
    monkeypatch.setattr(
        "launcher.ui.savebutton.FileDatabase.get_instance", lambda: Mock()
    )
    LauncherConfig.apply_game_overrides()
    LauncherConfig.set_game_override("monitor", "")
    context.config.set("title", "Changed game")

    SaveButton.save_config()

    saved = (tmp_path / "Example.fs-uae").read_text()
    assert "monitor = base-monitor" in saved
    assert "title = Changed game" in saved
    assert context.config.get("monitor") == ""


@pytest.mark.parametrize("base_edit", ["edited-monitor", "other-monitor", ""])
def test_custom_options_edits_preserve_base_and_active_override(
    game_config, monkeypatch, base_edit
):
    import launcher.ui.config.CustomOptionsPage as custom_options

    context, _, _ = game_config
    monkeypatch.setattr(custom_options, "fsgs", context)
    LauncherConfig.apply_game_overrides()
    LauncherConfig.set_game_override("monitor", "other-monitor")
    assert "monitor = base-monitor" in custom_options.initial_text()
    editor = Mock()
    editor.text_area.get_text.return_value = f"monitor = {base_edit}\n"

    custom_options.CustomOptionsPage.update_config(editor)

    assert LauncherConfig.copy_for_save()["monitor"] == base_edit
    assert LauncherConfig.get_game_base_value("monitor") == base_edit
    assert context.config.get("monitor") == "other-monitor"
    assert context.config.get("__changed") == "1"
    assert context.config.get("__ready") == "0"
    LauncherConfig.clear_game_override("monitor")
    assert context.config.get("monitor") == base_edit


def test_custom_options_noop_does_not_replace_base_with_overlay(
    game_config, monkeypatch
):
    import launcher.ui.config.CustomOptionsPage as custom_options

    context, _, _ = game_config
    monkeypatch.setattr(custom_options, "fsgs", context)
    LauncherConfig.apply_game_overrides()
    LauncherConfig.set_game_override("monitor", "other-monitor")
    editor = Mock()
    editor.text_area.get_text.return_value = custom_options.initial_text()

    custom_options.CustomOptionsPage.update_config(editor)

    assert LauncherConfig.copy_for_save()["monitor"] == "base-monitor"
    assert context.config.get("monitor") == "other-monitor"
    assert context.config.get("__changed") == "0"


def test_base_edit_before_first_override_is_restored(game_config):
    context, _, _ = game_config
    LauncherConfig.apply_game_overrides()
    LauncherConfig.set("monitor", "new-base")
    LauncherConfig.set_game_override("monitor", "other-monitor")
    LauncherConfig.clear_game_override("monitor")
    assert context.config.get("monitor") == "new-base"


def test_base_edit_is_written_to_config_and_override_remains_in_database(
    game_config, tmp_path, monkeypatch
):
    from launcher.ui.savebutton import SaveButton

    context, store, settings = game_config
    settings["config_name"] = "Example"
    monkeypatch.setattr(LauncherSettings, "set", settings.__setitem__)
    monkeypatch.setattr(
        "launcher.ui.savebutton.FSGSDirectories.get_configurations_dir",
        lambda: str(tmp_path),
    )
    monkeypatch.setattr(
        "launcher.ui.savebutton.Database.get_instance", lambda: Mock()
    )
    monkeypatch.setattr(
        "launcher.ui.savebutton.FileDatabase.get_instance", lambda: Mock()
    )
    LauncherConfig.apply_game_overrides()
    LauncherConfig.set_game_override("monitor", "other-monitor")
    LauncherConfig.set("monitor", "edited-monitor")
    SaveButton.save_config()

    assert "monitor = edited-monitor" in (tmp_path / "Example.fs-uae").read_text()
    assert store.get(LauncherConfig.game_override_identity()) == {
        "monitor": "other-monitor"
    }
    assert context.config.get("monitor") == "other-monitor"
    LauncherConfig.clear_game_override("monitor")
    assert context.config.get("monitor") == "edited-monitor"


def test_base_edit_refreshes_per_game_context(game_config):
    context, _, _ = game_config
    LauncherConfig.apply_game_overrides()
    LauncherConfig.set_game_override("monitor", "other-monitor")
    context.signal.notify.reset_mock()

    LauncherConfig.set("monitor", "edited-monitor")

    assert ("config", ("__game_override_context", "")) in [
        call.args for call in context.signal.notify.call_args_list
    ]


def test_failed_override_read_preserves_base_and_disables_editing(
    game_config, monkeypatch, caplog
):
    context, store, _ = game_config
    monkeypatch.setattr(
        store, "get", Mock(side_effect=sqlite3.DatabaseError("corrupt"))
    )

    LauncherConfig.apply_game_overrides()

    assert context.config.get("monitor") == "base-monitor"
    assert LauncherConfig.get_game_overrides() == {}
    assert not LauncherConfig.game_overrides_available()
    assert "Could not load game overrides" in caplog.text
    with pytest.raises(ValueError, match="not available"):
        LauncherConfig.set_game_override("monitor", "other-monitor")


def test_context_notified_after_load_and_even_unchanged_edits(game_config):
    context, _, _ = game_config
    LauncherConfig.apply_game_overrides()
    assert context.signal.notify.call_args.args == (
        "config", ("__game_override_context", "")
    )
    LauncherConfig.set_game_override("monitor", "base-monitor")
    LauncherConfig.clear_game_override("monitor")
    events = [
        call.args for call in context.signal.notify.call_args_list
        if call.args == ("config", ("__game_override_context", ""))
    ]
    assert len(events) == 3


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
    monkeypatch.setattr(LauncherConfig, "get", lambda key: "")
    monkeypatch.setattr(
        LauncherConfig, "get_game_overrides", lambda: {"monitor": ""}
    )
    monkeypatch.setattr(LauncherSettings, "get", lambda key: "global-display")

    assert LauncherConfig.effective_monitor() == ""


def test_monitor_without_override_uses_global_setting(monkeypatch):
    monkeypatch.setattr(LauncherConfig, "get", lambda key: "")
    monkeypatch.setattr(LauncherConfig, "get_game_overrides", lambda: {})
    monkeypatch.setattr(LauncherSettings, "get", lambda key: "global-display")

    assert LauncherConfig.effective_monitor() == "global-display"
