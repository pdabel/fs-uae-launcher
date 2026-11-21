"""The lobby server list and the netplay settings behind it."""

import pytest

from fsbc.settings import Settings
from launcher.launcher_settings import LauncherSettings
from launcher.netplay.lobby_servers import (
    add_server,
    normalize_server,
    remove_server,
    split_servers,
)


@pytest.mark.parametrize(
    "text, want",
    [
        ("netplay.example.net", "netplay.example.net"),
        ("  Netplay.Example.NET  ", "netplay.example.net"),
        ("netplay.example.net:25101", "netplay.example.net"),
        ("203.0.113.4:25200", "203.0.113.4:25200"),
        ("[2001:db8::1]:25200", "[2001:db8::1]:25200"),
        ("[2001:db8::1]:25101", "2001:db8::1"),
        ("2001:db8::1", "2001:db8::1"),
    ],
)
def test_normalize(text, want):
    assert normalize_server(text) == want


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "host:port",
        "host:0",
        "host:70000",
        "a b",
        "http://x",
        ":25101",
    ],
)
def test_normalize_refuses(text):
    with pytest.raises(ValueError):
        normalize_server(text)


def test_split_drops_blanks_bad_entries_and_duplicates():
    value = "a.example; ;B.example:25101;b.example;bad host;c.example:25200"
    assert split_servers(value) == [
        "a.example",
        "b.example",
        "c.example:25200",
    ]


def test_add_and_remove():
    value = add_server("", "One.example")
    value = add_server(value, "two.example:25200")
    assert value == "one.example;two.example:25200"
    with pytest.raises(ValueError, match="already"):
        add_server(value, "ONE.example:25101")
    with pytest.raises(ValueError):
        add_server(value, "not a host")
    assert remove_server(value, "one.example") == "two.example:25200"
    assert remove_server(value, "missing.example") == value


@pytest.fixture
def settings(monkeypatch):
    s = Settings()
    s._loaded = True
    s._atexit_registered = True
    s.verbose = False
    monkeypatch.setattr(Settings, "_instance", s)
    return s


def test_irc_nick_is_copied_to_an_empty_netplay_name(settings):
    settings.set("irc_nick", "Dave")
    LauncherSettings.copy_irc_nick_to_netplay_name()
    assert settings.get("netplay_name") == "Dave"

    settings.set("irc_nick", "Other")
    LauncherSettings.copy_irc_nick_to_netplay_name()
    assert settings.get("netplay_name") == "Dave"


def test_netplay_name(settings):
    settings.set("irc_nick", "Nick")
    assert LauncherSettings.get_netplay_name() == "Nick"
    settings.set("netplay_name", "  Dave  ")
    assert LauncherSettings.get_netplay_name() == "Dave"
    assert LauncherSettings.get_irc_nick() == "Dave"
    # The lobby allows 32 bytes: a multi-byte name is cut on a character.
    settings.set("netplay_name", "é" * 20)
    assert LauncherSettings.get_netplay_name() == "é" * 16


def test_netplay_host_port(settings):
    assert LauncherSettings.get_netplay_host_port() == 25101
    settings.set("netplay_host_port", "25200")
    assert LauncherSettings.get_netplay_host_port() == 25200
    settings.set("netplay_host_port", "80")
    assert LauncherSettings.get_netplay_host_port() == 1024
    settings.set("netplay_host_port", "junk")
    assert LauncherSettings.get_netplay_host_port() == 25101
