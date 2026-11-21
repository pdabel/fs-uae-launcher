import os
import tempfile
from configparser import ConfigParser

import fsbc.settings
from fsbc.application import Application
from fsbc.paths import Paths
from fsbc.settings import Settings


def test_load_save():
    fd, path = tempfile.mkstemp()
    os.close(fd)
    fsbc.settings.set_path(path)
    fsbc.settings.load()

    fsbc.settings.set("Key-å", "Value-å")
    fsbc.settings.save()
    fsbc.settings.unload()

    fsbc.settings.load()

    value = fsbc.settings.get("Key-å")
    assert value == "Value-å"
    fsbc.settings.unload()


def test_mypy():
    import fstd.mypy

    fstd.mypy.check_module(fsbc.settings.__name__)


def loaded_settings(values, path=None):
    settings = Settings(path=path)
    settings.values.update(values)
    settings._loaded = True
    return settings


def test_save_writes_application_version(tmp_path, monkeypatch):
    monkeypatch.setattr(Application, "app_version", "3.2.1")
    path = tmp_path / "Settings.ini"
    loaded_settings({"fullscreen": "1"}, path=str(path)).save()

    cp = ConfigParser(interpolation=None)
    cp.read(path, encoding="UTF-8")
    assert cp.get("settings", "fullscreen") == "1"
    assert cp.get("launcher", "version") == "3.2.1"


def test_save_without_application_version(tmp_path, monkeypatch):
    monkeypatch.setattr(Application, "app_version", "")
    path = tmp_path / "Settings.ini"
    loaded_settings({}, path=str(path)).save()

    cp = ConfigParser(interpolation=None)
    cp.read(path, encoding="UTF-8")
    assert cp.get("launcher", "version") == "0.0.0"


def test_expand_config_prefix(monkeypatch):
    settings = loaded_settings(
        {"config_path": "/amiga/Configurations/Game.fs-uae"}
    )
    monkeypatch.setattr(Settings, "_instance", settings)
    assert (
        Paths.expand_path("$CONFIG/Disk 1.adf")
        == "/amiga/Configurations/Disk 1.adf"
    )


def test_expand_config_prefix_without_config(monkeypatch):
    monkeypatch.setattr(Settings, "_instance", loaded_settings({}))
    assert Paths.expand_path("$CONFIG/Disk 1.adf") == "$CONFIG/Disk 1.adf"
