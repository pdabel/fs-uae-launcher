from types import SimpleNamespace

from fsgs.displays import (
    display_id,
    display_label,
    fsuae_monitor,
    screen_index,
)


def display(name, horizontal=0, vertical=0, serial=""):
    geometry = SimpleNamespace(
        x=lambda: horizontal,
        y=lambda: vertical,
        width=lambda: 1920,
        height=lambda: 1080,
    )
    return SimpleNamespace(
        name=lambda: name,
        manufacturer=lambda: "Test Manufacturer",
        model=lambda: "Test Display",
        serialNumber=lambda: serial,
        geometry=lambda: geometry,
        refreshRate=lambda: 60.0,
    )


def test_selected_display_survives_enumeration_and_position_changes():
    first = display("DP-1", -1920)
    second = display("HDMI-1", serial="second")
    selected = display_id(second)
    assert screen_index([first, second], selected, first) == 1
    moved = display("HDMI-1", 0, -1080, "second")
    assert screen_index([moved, first], selected, first) == 0


def test_disconnected_monitor_falls_back_to_primary():
    first = display("DP-1")
    primary = display("HDMI-1", 1920)
    assert (
        screen_index([first, primary], display_id(display("Missing")), primary)
        == 1
    )
    assert screen_index([first, primary], "", primary) == 1
    assert screen_index([first, primary], "primary", primary) == 1
    assert screen_index([], "primary") is None


def test_legacy_positions_remain_readable_with_vertical_displays():
    bottom = display("Bottom", 0, 1080)
    top = display("Top")
    assert screen_index([bottom, top], "left", bottom) == 1
    assert screen_index([bottom, top], "right", bottom) == 0


def test_display_label_contains_identity_resolution_and_position():
    label = display_label(display("DP-1", -1920, 100))
    assert "DP-1" in label
    assert "Test Display" in label
    assert "1920x1080" in label
    assert "-1920,100" in label


def test_native_fsuae_fullscreen_translation_does_not_use_qt_enumeration_order():
    left = display("DP-1", -1920)
    right = display("HDMI-1")
    assert fsuae_monitor([right, left], display_id(left), right) == "left"
    assert fsuae_monitor([right, left], display_id(right), left) == "right"
    assert (
        fsuae_monitor([right, left], display_id(display("Missing")), right)
        == "right"
    )
    monitors = [display(str(index), index * 1920) for index in range(4)]
    assert [
        fsuae_monitor(monitors, display_id(screen)) for screen in monitors
    ] == ["left", "middle-left", "middle-right", "right"]


def test_native_fsuae_reports_layouts_its_fullscreen_option_cannot_represent():
    monitors = [display(str(index), index * 1920) for index in range(5)]
    assert fsuae_monitor(monitors, display_id(monitors[2])) is None
    stacked = [display("top"), display("bottom", 0, 1080)]
    assert fsuae_monitor(stacked, display_id(stacked[1])) is None
    assert fsuae_monitor([], "primary") is None


def test_fsuae_starts_on_selected_display_not_launcher_monitor(monkeypatch):
    import importlib

    from fsgs.amiga.fsuae import FSUAE
    from fsgs.drivers.gamedriver import GameDriver
    from launcher.launcher_config import LauncherConfig
    from launcher.launcher_settings import LauncherSettings

    first = display("DP-1")
    selected = display("HDMI-1", -1920)
    application = SimpleNamespace(
        screens=lambda: [first, selected], primaryScreen=lambda: first
    )
    monkeypatch.setattr(
        importlib.import_module("fsui.qt"), "init_qt", lambda: application
    )
    monkeypatch.setattr(LauncherConfig, "get", lambda key: "")
    settings = {
        "monitor": display_id(selected),
        "window_width": "960",
        "window_height": "540",
    }
    monkeypatch.setattr(
        LauncherSettings, "get", lambda key: settings.get(key, "")
    )
    assert GameDriver.screen_rect_for_monitor(settings["monitor"]) == (
        -1920,
        0,
        1920,
        1080,
    )
    assert GameDriver.screen_index_for_monitor(settings["monitor"]) == 1
    args = []
    environment = {}
    FSUAE.center_window(args, environment)
    assert args == ["--monitor=left", "--window-x=-1440", "--window-y=270"]
    assert environment["SDL_VIDEO_WINDOW_POS"] == "-1440,270"


def test_monitor_identity_is_not_written_to_emulator_config():
    from fsgs.amiga.configwriter import ConfigWriter

    config = ConfigWriter(
        {"monitor": display_id(display("DP-1")), "amiga_model": "A500"}
    ).create_fsuae_config()
    assert "amiga_model = A500" in config
    assert not any(line.startswith("monitor =") for line in config)


def test_actual_fsuae_process_receives_selected_screen_position(monkeypatch):
    from unittest.mock import Mock
    from fsgs.amiga.fsuae import FSUAE
    from fsgs.drivers.gamedriver import GameDriver
    from launcher.launcher_config import LauncherConfig
    from launcher.launcher_settings import LauncherSettings

    selected = display_id(display("HDMI-1"))
    settings = {
        "monitor": selected,
        "window_width": "960",
        "window_height": "540",
    }
    monkeypatch.setattr(
        LauncherSettings, "get", lambda key: settings.get(key, "")
    )
    monkeypatch.setattr(LauncherConfig, "get", lambda key: "")
    monkeypatch.setattr(
        GameDriver,
        "screen_rect_for_monitor",
        lambda monitor: (1920, -1080, 1920, 1080),
    )
    monkeypatch.setattr(
        GameDriver, "fsuae_monitor_for_monitor", lambda monitor: "right"
    )
    monkeypatch.setattr(
        "fsgs.amiga.fsuae.PluginExecutableFinder.find_executable",
        lambda self, name: "/emulator/fs-uae",
    )
    monkeypatch.setattr(
        FSUAE, "add_environment_from_settings", lambda env: None
    )
    monkeypatch.delenv("SDL_VIDEODRIVER", raising=False)
    monkeypatch.delenv("__GL_SYNC_TO_VBLANK", raising=False)
    process = Mock()
    monkeypatch.setattr("fsgs.amiga.fsuae.subprocess.Popen", process)
    FSUAE.start_with_args(["/temporary/config.fs-uae"])
    args = process.call_args.args[0]
    assert args == [
        "/emulator/fs-uae",
        "/temporary/config.fs-uae",
        "--monitor=right",
        "--window-x=2400",
        "--window-y=-810",
    ]
    assert (
        process.call_args.kwargs["env"]["SDL_VIDEO_WINDOW_POS"] == "2400,-810"
    )


def test_generic_driver_uses_same_monitor_for_window_placement(monkeypatch):
    from fsgs.drivers.gamedriver import GameDriver
    from launcher.launcher_config import LauncherConfig
    from launcher.launcher_settings import LauncherSettings

    monkeypatch.setattr(LauncherConfig, "get", lambda key: "")
    monkeypatch.setattr(LauncherSettings, "get", lambda key: "")
    driver = SimpleNamespace(screen_rect=lambda: (-1920, 0, 1920, 1080))
    environment = {}
    GameDriver.update_environment_with_centering_info(driver, environment)
    assert environment["SDL_VIDEO_WINDOW_POS"] == "-1440,270"
    assert environment["FSGS_WINDOW_CENTER"] == "-960,540"


def test_refresh_rate_uses_selected_qt_screen_when_xrandr_does_not_match(
    monkeypatch,
):
    import importlib
    from fsgs.drivers.gamedriver import GameDriver

    screen = display("DP-1")
    application = SimpleNamespace(
        screens=lambda: [screen], primaryScreen=lambda: screen
    )
    monkeypatch.setattr(
        importlib.import_module("fsui.qt"), "init_qt", lambda: application
    )
    tool = SimpleNamespace(
        screens_xrandr=lambda: {(0, 0, 800, 600): {"refresh_rate": 50}}
    )
    monkeypatch.setattr(
        "fsgs.drivers.gamedriver.RefreshRateTool", lambda: tool
    )
    assert GameDriver.screen_refresh_rate_for_monitor(display_id(screen)) == 60
