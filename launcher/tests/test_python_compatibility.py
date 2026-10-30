import hashlib
import locale
import sys

import pytest

from launcher.i18n import _default_language
from launcher.launcherapp import LauncherApp


@pytest.mark.parametrize("relative", [None, ".", "Amiga Data"])
def test_portable_data_location(tmp_path, monkeypatch, relative):
    import fsboot

    marker = tmp_path / "Portable.ini"
    marker.write_text(
        "" if relative is None else "[launcher]\nbase_dir = " + relative + "\n"
    )
    monkeypatch.setattr(sys, "argv", ["fs-uae-launcher"])
    monkeypatch.setattr(fsboot, "portable_dir", lambda: str(tmp_path))
    expected = tmp_path if relative in (None, ".") else tmp_path / relative
    assert fsboot._getBaseDirectoryBeforeNormalization() == str(expected)


@pytest.mark.parametrize(
    "environment,expected",
    [({}, None),
     ({"LC_ALL": "fr_FR.UTF-8", "LANG": "de_DE.UTF-8"}, "fr_FR"),
     ({"LC_CTYPE": "UTF-8"}, None),
     ({"LANG": "C"}, None),
    ({"LANG": "C.UTF-8"}, locale.normalize("C.UTF-8").split(".", 1)[0]),
     ({"LANGUAGE": "de_DE:fr_FR"}, "de_DE"),
     ({"LANG": "sr_RS.UTF-8@latin"}, "sr_RS"),
     ({"LANG": "de_DE@euro"}, "de_DE")],
)
def test_default_language(monkeypatch, environment, expected):
    for variable in ("LC_ALL", "LC_CTYPE", "LANG", "LANGUAGE"):
        monkeypatch.delenv(variable, raising=False)
    for variable, value in environment.items():
        monkeypatch.setenv(variable, value)
    assert _default_language() == expected


def test_plugin_registration_and_reload(tmp_path, monkeypatch):
    path = tmp_path / "example.PY"
    path.write_text(
        "import importlib, sys\n"
        "assert importlib.import_module(__name__) is sys.modules[__name__]\n"
        "loads = globals().get('loads', 0) + 1\n"
        "def fsgs_init():\n"
        "    global initialized\n"
        "    initialized = (fsgs, plugin_dir)\n"
    )
    name = "plugin_" + hashlib.sha1(str(path).encode("UTF-8")).hexdigest()
    monkeypatch.setitem(sys.modules, name, None)
    sys.modules.pop(name)
    LauncherApp._load_plugins(str(tmp_path))
    plugin = sys.modules[name]
    assert plugin.loads == 1
    assert plugin.initialized[1] == str(tmp_path)
    assert plugin.initialized[0] is plugin.fsgs
    LauncherApp._load_plugins(str(tmp_path))
    assert sys.modules[name] is plugin
    assert plugin.loads == 2


def test_failed_plugin_import_is_removed(tmp_path, monkeypatch, capsys):
    path = tmp_path / "broken.py"
    path.write_text("raise RuntimeError('plugin failed')\n")
    name = "plugin_" + hashlib.sha1(str(path).encode("UTF-8")).hexdigest()
    monkeypatch.setitem(sys.modules, name, None)
    sys.modules.pop(name)
    LauncherApp._load_plugins(str(tmp_path))
    assert name not in sys.modules
    assert "plugin failed" in capsys.readouterr().err