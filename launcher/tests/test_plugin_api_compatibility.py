import hashlib
import importlib
import sys

import pytest


@pytest.mark.parametrize(
    "module,names",
    [
        (
            "fsbc.fs",
            [
                "cache",
                "get_lib_dir",
                "get_app_id",
                "get_app_data_dir",
                "get_app_config_dir",
                "cause",
                "from_utf8_str",
                "to_utf8_str",
                "utf8",
                "utf8_safe",
                "unicode_safe",
                "Version",
                "split_version",
                "compare_versions",
                "EXCEPTION",
            ],
        ),
        ("fsbc.path", ["str_path"]),
        ("fsbc.user", ["get_desktop_dir", "get_pictures_dir"]),
        ("fsbc.util", ["chained_exception"]),
        ("fsbc.debug", ["AdditionalInfo"]),
        ("fsgs.GameNameUtil", ["GameNameUtil"]),
        ("fsgs.amiga.adf", ["checksum_block"]),
        (
            "fsgs.input.inputdevice",
            [
                "InputDeviceInfo",
                "InputDeviceNotFoundException",
            ],
        ),
        ("fsgs.knownfiles", ["KnownFilePath"]),
        ("fsgs.network", ["openretro_scheme"]),
    ],
)
def test_removed_public_plugin_names_remain_importable(module, names):
    imported = importlib.import_module(module)
    for name in names:
        assert hasattr(imported, name), f"{module}.{name}"


def test_third_party_python_plugin_initializes_with_legacy_api(tmp_path):
    from launcher.launcherapp import LauncherApp

    path = tmp_path / "compatibility.py"
    path.write_text(
        "from fsbc.fs import Version, from_utf8_str\n"
        "from fsgs.GameNameUtil import GameNameUtil\n"
        "from fsgs.input.inputdevice import InputDeviceInfo\n"
        "initialized = False\n"
        "def fsgs_init():\n"
        "    global initialized\n"
        "    assert fsgs is not None\n"
        "    assert from_utf8_str(b'plugin') == 'plugin'\n"
        "    assert InputDeviceInfo().get_type() == 'TYPE_KEYBOARD'\n"
        "    initialized = True\n"
    )
    name = "plugin_" + hashlib.sha1(str(path).encode("UTF-8")).hexdigest()
    try:
        LauncherApp._load_plugins(str(tmp_path))
        assert sys.modules[name].initialized
    finally:
        sys.modules.pop(name, None)


def test_legacy_settings_drive_limits():
    from fsbc.settings import Settings
    from fsgs.amiga.amiga import Amiga

    settings = Settings()
    settings._loaded = True
    for name, default in (
        ("max_floppy_drives", Amiga.MAX_FLOPPY_DRIVES),
        ("max_floppy_images", Amiga.MAX_FLOPPY_IMAGES),
        ("max_cdrom_drives", Amiga.MAX_CDROM_DRIVES),
        ("max_cdrom_images", Amiga.MAX_CDROM_IMAGES),
        ("max_hard_drives", Amiga.MAX_HARD_DRIVES),
    ):
        assert getattr(settings, name) == default
        settings.values[name] = "2"
        assert getattr(settings, name) == 2


def test_legacy_initializer_call_contract(monkeypatch):
    module = importlib.import_module("fsbc.init")
    monkeypatch.setattr(module, "init_called", False)
    monkeypatch.setattr(module, "unicode_patched", False)
    monkeypatch.setattr(module, "logging_enabled", False)
    monkeypatch.setattr(module, "exception_handler_enabled", False)
    module.initialize_application(None, None, False, False, False)
    assert module.init_called
    assert not module.unicode_patched
    assert not module.logging_enabled
    assert not module.exception_handler_enabled


def test_legacy_filesystem_helpers_use_python3_paths(tmp_path, monkeypatch):
    import fsbc.fs

    monkeypatch.setenv("LIB_DIR", str(tmp_path))
    assert fsbc.fs.get_lib_dir.__wrapped__() == str(tmp_path)
    monkeypatch.delenv("LIB_DIR")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "lib").mkdir()
    assert fsbc.fs.get_lib_dir.__wrapped__() == str(tmp_path / "lib")
    monkeypatch.setattr(fsbc.fs, "get_data_dir", lambda: str(tmp_path))
    assert fsbc.fs.get_app_data_dir("plugin") == str(tmp_path / "plugin")
    assert (tmp_path / "plugin").is_dir()
    assert fsbc.fs.from_utf8_str(b"plugin") == "plugin"
    assert fsbc.fs.to_utf8_str("plugin") == "plugin"
    assert fsbc.fs.unicode_safe(b"plugin") == "b'plugin'"
    assert fsbc.fs.utf8("plugin") == b"plugin"


def test_legacy_adf_checksum_and_driver_helpers():
    from fsgs.amiga.adf import checksum_block, verify_block
    from fsgs.drivers.gamedriver import GameDriver
    from launcher.option import Option
    from types import SimpleNamespace

    block = bytearray(512)
    block[0:4] = (2).to_bytes(4, "big")
    block[20:24] = checksum_block(block).to_bytes(4, "big")
    assert verify_block(block)
    driver = SimpleNamespace(
        options={Option.PLATFORM: "amiga"},
        game_name=lambda: "Test Game",
    )
    assert GameDriver.get_platform_name(driver) == "Amiga"
    assert GameDriver.screenshots_name(driver) == "Test Game"
