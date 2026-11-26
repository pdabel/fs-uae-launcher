from unittest.mock import Mock

import pytest
import requests

import launcher.update_manager as update_manager
from launcher.update_manager import UpdateManager


@pytest.fixture
def update_check(monkeypatch):
    response = Mock(text=" 99.0.0\n")
    get = Mock(return_value=response)
    set_setting = Mock()
    broadcast = Mock()
    monkeypatch.setattr(update_manager.requests, "get", get)
    monkeypatch.setattr(update_manager.launcher.version, "VERSION", "1.0.0")
    monkeypatch.setattr(UpdateManager, "series", lambda: "stable")
    monkeypatch.setattr(update_manager.LauncherSettings, "set", set_setting)
    monkeypatch.setattr(update_manager.LauncherSignal, "broadcast", broadcast)
    return get, response, set_setting, broadcast


def test_update_check_has_timeout_and_announces_new_version(update_check):
    get, response, set_setting, broadcast = update_check

    UpdateManager._update_thread_function()

    assert get.call_args.kwargs == {"timeout": 10}
    assert get.call_args.args[0].startswith(
        "https://fs-uae.net/stable/latest-"
    )
    response.raise_for_status.assert_called_once_with()
    set_setting.assert_called_once_with("__update_available", "99.0.0")
    broadcast.assert_called_once_with(
        "update_available", "99.0.0", "https://fs-uae.net/stable/download/"
    )


@pytest.mark.parametrize("version", ["1.0.0", "0.9.0", "9.9.9"])
def test_update_check_does_not_announce_old_or_placeholder_versions(
    update_check, version
):
    _, response, set_setting, broadcast = update_check
    response.text = version

    UpdateManager._update_thread_function()

    set_setting.assert_not_called()
    broadcast.assert_not_called()


@pytest.mark.parametrize("failure", ["timeout", "http"])
def test_update_check_reports_request_errors_without_announcing(
    update_check, failure, capsys
):
    get, response, set_setting, broadcast = update_check
    if failure == "timeout":
        get.side_effect = requests.Timeout("check timed out")
    else:
        response.raise_for_status.side_effect = requests.HTTPError(
            "bad status"
        )

    UpdateManager.update_thread_function()

    assert ("check timed out" if failure == "timeout" else "bad status") in (
        capsys.readouterr().err
    )
    set_setting.assert_not_called()
    broadcast.assert_not_called()
