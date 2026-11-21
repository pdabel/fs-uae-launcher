import fsbc.i18n
from fsgs.res import gettext


def test_gettext_uses_installed_hook(monkeypatch):
    monkeypatch.setattr(fsbc.i18n, "_gettext", {"Stop": "Arrêter"}.get)
    assert gettext("Stop") == "Arrêter"
