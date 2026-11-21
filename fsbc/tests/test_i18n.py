import fsbc.i18n
from fsbc.init import initialize_application


def test_untranslated_without_hook(monkeypatch):
    monkeypatch.setattr(fsbc.i18n, "_gettext", None)
    assert fsbc.i18n.gettext("Stop") == "Stop"


def test_initialize_application_installs_gettext(monkeypatch):
    monkeypatch.setattr(fsbc.i18n, "_gettext", None)
    initialize_application(
        gettext={"Stop": "Arrêter"}.get, enable_exception_handler=False
    )
    assert fsbc.i18n.gettext("Stop") == "Arrêter"
