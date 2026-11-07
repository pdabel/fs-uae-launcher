import sqlite3
from contextlib import closing

import pytest

from launcher.netplay.command_history import CommandHistory


def test_history_persists_and_restores_draft(tmp_path):
    path = tmp_path / "history.sqlite"
    CommandHistory(path).add("/join #amiga")
    CommandHistory(path).add("/hostgame localhost:25101 2")
    history = CommandHistory(path)
    assert (
        history.previous("unfinished draft") == "/hostgame localhost:25101 2"
    )
    assert history.previous("ignored") == "/join #amiga"
    assert history.previous("ignored") == "/join #amiga"
    assert history.next("ignored") == "/hostgame localhost:25101 2"
    assert history.next("ignored") == "unfinished draft"
    assert history.next("current input") == "current input"


def test_history_is_bounded_and_repeated_commands_move_to_latest(tmp_path):
    history = CommandHistory(tmp_path / "history.sqlite")
    for number in range(history.limit + 5):
        history.add(f"/join #game-{number}")
    history.add("/join #game-5")
    assert history.previous("") == "/join #game-5"
    assert len(history.entries) == history.limit
    assert len(set(history.entries)) == history.limit
    assert "/join #game-0" not in history.entries


@pytest.mark.parametrize(
    "command",
    [
        "",
        "hello everyone",
        "/msg NickServ identify secret",
        "/notice NickServ secret",
        "/raw PASS secret",
        "/oper admin secret",
        "/identify secret",
        "/hostgame localhost 2 secret",
        "/startgame localhost 2 secret",
        "/startserver localhost  2",
        "/join #game secret",
        "/joingame host game-id extra",
        "/set password secret",
        "/set database_auth secret",
        "/set token secret",
        "/mode #game +k secret",
        "/join #game\n/oper admin secret",
    ],
)
def test_private_input_is_not_stored(tmp_path, command):
    path = tmp_path / "history.sqlite"
    history = CommandHistory(path)
    history.add(command)
    assert not path.exists()


def test_clear_deletes_persisted_history_and_resets_navigation(tmp_path):
    path = tmp_path / "history.sqlite"
    history = CommandHistory(path)
    history.add("/recheck")
    assert history.previous("draft") == "/recheck"
    history.clear()
    assert history.next("current") == "current"
    assert CommandHistory(path).previous("new draft") == "new draft"
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute(
            "SELECT count(*) FROM command_history"
        ).fetchone() == (0,)


def test_saved_command_is_parameterized_and_database_is_private(tmp_path):
    path = tmp_path / "history.sqlite"
    history = CommandHistory(path)
    text = "/join #';DROP/**/TABLE/**/command_history;--"
    history.add(text)
    assert CommandHistory(path).previous("") == text
    assert path.stat().st_mode & 0o777 == 0o600


def test_manual_join_and_configuration_commands_are_recalled(tmp_path):
    history = CommandHistory(tmp_path / "history.sqlite")
    history.add("/joingame localhost:25101 game-id")
    history.add("/set floppy_drive_0 $BASE/Floppies/My Game.adf")
    assert (
        history.previous("")
        == "/set floppy_drive_0 $BASE/Floppies/My Game.adf"
    )
    assert history.previous("") == "/joingame localhost:25101 game-id"
