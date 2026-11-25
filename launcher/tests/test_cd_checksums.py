import hashlib
import threading
from unittest.mock import Mock

import pytest

from fsgs.amiga.amigacontext import AmigaContext
from fsgs.Config import Config
from fsgs.filedatabase import FileDatabase
from launcher.launcher_config import LauncherConfig


@pytest.fixture
def cd_context(tmp_path, monkeypatch):
    import fsgs.amiga.amigacontext as module

    context = Mock()
    context.config = Config(context)
    context.amiga = AmigaContext(context)
    jobs = []
    callbacks = []
    database = Mock()
    database.find_file.return_value = {
        "sha1": None,
        "size": None,
        "mtime": None,
    }
    monkeypatch.setattr(FileDatabase, "static_files", {})
    monkeypatch.setattr(FileDatabase, "get_instance", lambda: database)
    monkeypatch.setattr(
        module.FSGSDirectories, "get_cdroms_dir", lambda: str(tmp_path)
    )
    monkeypatch.setattr(module.Paths, "contract_path", lambda path, _: path)
    monkeypatch.setattr(module.Paths, "expand_path", lambda path: path)
    monkeypatch.setattr(module, "call_after", callbacks.append)

    class Worker:
        def __init__(self, target, **_):
            self.target = target

        def start(self):
            jobs.append(self.target)

    monkeypatch.setattr(module, "Thread", Worker)

    def complete():
        for job in jobs:
            worker = threading.Thread(target=job)
            worker.start()
            worker.join(timeout=5)
            assert not worker.is_alive()
        jobs.clear()
        for callback in callbacks:
            callback()
        callbacks.clear()

    return context, database, complete


def test_insert_cd_hashes_on_worker_and_applies_on_dispatch(
    cd_context, tmp_path, monkeypatch
):
    context, database, complete = cd_context
    path = tmp_path / "game.iso"
    path.write_bytes(b"CD image")
    main_thread = threading.get_ident()
    database.find_file.side_effect = lambda **_: (
        pytest.fail("Database lookup ran on the caller's thread")
        if threading.get_ident() == main_thread
        else {"sha1": None, "size": None, "mtime": None}
    )

    context.amiga.insert_cd(0, str(path))

    assert context.config.get("cdrom_drive_0") == ""
    assert context.config.get("x_cdrom_drive_0_sha1") == ""
    database.find_file.assert_not_called()
    complete()
    sha1 = hashlib.sha1(b"CD image").hexdigest()
    assert context.config.get("cdrom_drive_0") == str(path)
    assert context.config.get("x_cdrom_drive_0_sha1") == sha1
    assert FileDatabase.static_files[sha1]["path"] == str(path)


def test_loaded_large_cd_reuses_scanned_checksum(
    cd_context, tmp_path, monkeypatch
):
    import launcher.launcher_config as module

    context, database, complete = cd_context
    path = tmp_path / "large.iso"
    with path.open("wb") as stream:
        stream.truncate(65 * 1024 * 1024)
    sha1 = "a" * 40
    database.find_file.return_value = {
        "sha1": bytes.fromhex(sha1),
        "size": path.stat().st_size,
        "mtime": int(path.stat().st_mtime),
    }
    checksum = Mock(side_effect=AssertionError("Cached CD was rehashed"))
    monkeypatch.setattr(
        "fsgs.amiga.amigacontext.ChecksumTool.checksum", checksum
    )
    monkeypatch.setattr(module, "fsgs", context)
    monkeypatch.setattr(
        LauncherConfig, "update_kickstart_in_config_dict", lambda _: None
    )
    for name in (
        "_game_base_identity",
        "_game_base_values",
        "_game_override_values",
        "_game_overrides_available",
    ):
        monkeypatch.setattr(
            LauncherConfig, name, getattr(LauncherConfig, name)
        )

    LauncherConfig.load({"cdrom_drive_0": str(path)})

    assert context.config.get("x_cdrom_drive_0_sha1") == ""
    complete()
    assert context.config.get("x_cdrom_drive_0_sha1") == sha1
    checksum.assert_not_called()


def test_large_unscanned_cd_is_hashed_without_size_limit(
    cd_context, tmp_path, monkeypatch
):
    context, _, complete = cd_context
    path = tmp_path / "unscanned.iso"
    with path.open("wb") as stream:
        stream.truncate(65 * 1024 * 1024)
    checksum = Mock(return_value="c" * 40)
    monkeypatch.setattr(
        "fsgs.amiga.amigacontext.ChecksumTool.checksum", checksum
    )
    context.amiga.insert_cd(0, str(path))
    checksum.assert_not_called()
    complete()
    checksum.assert_called_once_with(str(path))
    assert context.config.get("x_cdrom_drive_0_sha1") == "c" * 40


def test_stale_scanned_checksum_is_not_reused(cd_context, tmp_path):
    context, database, complete = cd_context
    path = tmp_path / "changed.iso"
    path.write_bytes(b"new CD data")
    database.find_file.return_value = {
        "sha1": bytes.fromhex("a" * 40),
        "size": 1,
        "mtime": int(path.stat().st_mtime),
    }
    context.amiga.insert_cd(0, str(path))
    complete()
    assert (
        context.config.get("x_cdrom_drive_0_sha1")
        == hashlib.sha1(b"new CD data").hexdigest()
    )


@pytest.mark.parametrize("failure", ["missing", "unreadable"])
def test_cd_checksum_failure_is_logged(
    cd_context, tmp_path, monkeypatch, caplog, failure
):
    context, _, complete = cd_context
    path = tmp_path / "broken.iso"
    if failure == "unreadable":
        path.write_bytes(b"CD")
        monkeypatch.setattr(
            "fsgs.amiga.amigacontext.ChecksumTool.checksum",
            Mock(side_effect=PermissionError("access denied")),
        )
    context.amiga.insert_cd(0, str(path))
    complete()
    assert context.config.get("x_cdrom_drive_0_sha1") == ""
    assert "Could not checksum CD image" in caplog.text
    assert str(path) in caplog.text


def test_ejecting_or_replacing_cd_discards_late_results(cd_context, tmp_path):
    context, _, complete = cd_context
    first = tmp_path / "first.iso"
    first.write_bytes(b"first")
    second = tmp_path / "second.iso"
    second.write_bytes(b"second")
    context.amiga.insert_cd(0, str(first))
    context.amiga.eject_cd(0)
    complete()
    assert context.config.get("x_cdrom_drive_0_sha1") == ""

    context.amiga.insert_cd(0, str(first))
    context.amiga.insert_cd(0, str(second))
    complete()
    assert (
        context.config.get("x_cdrom_drive_0_sha1")
        == hashlib.sha1(b"second").hexdigest()
    )


def test_multi_cd_selection_hashes_each_path_once_and_clears_old_slots(
    cd_context, tmp_path
):
    context, database, complete = cd_context
    paths = [tmp_path / "first.iso", tmp_path / "second.iso"]
    for path in paths:
        path.write_bytes(path.name.encode())
    context.config.set("cdrom_image_2", "old.iso")
    context.amiga.insert_cd_images([str(path) for path in paths])
    complete()
    assert context.config.get("cdrom_image_2") == ""
    assert database.find_file.call_count == 2
    first_sha1 = hashlib.sha1(paths[0].name.encode()).hexdigest()
    assert context.config.get("x_cdrom_drive_0_sha1") == first_sha1
    assert context.config.get("x_cdrom_image_0_sha1") == first_sha1
    assert (
        context.config.get("x_cdrom_image_1_sha1")
        == hashlib.sha1(paths[1].name.encode()).hexdigest()
    )


def test_supplied_cd_checksum_is_preserved(cd_context):
    context, database, complete = cd_context
    context.amiga.insert_cd(0, "already-resolved.iso", sha1="b" * 40)
    complete()
    assert context.config.get("x_cdrom_drive_0_sha1") == "b" * 40
    database.find_file.assert_not_called()


def test_cd_from_archive_and_url(cd_context, tmp_path):
    from zipfile import ZipFile

    context, _, complete = cd_context
    path = tmp_path / "media.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("game.iso", b"archived CD")
    context.amiga.insert_cd(0, f"{path}#/game.iso")
    complete()
    assert (
        context.config.get("x_cdrom_drive_0_sha1")
        == hashlib.sha1(b"archived CD").hexdigest()
    )

    url = "https://example.invalid/game.iso"
    context.amiga.insert_cd(0, url)
    complete()
    assert context.config.get("x_cdrom_drive_0_sha1") == url


def test_netplay_waits_for_cd_checksum_before_creating_a_game(
    cd_context, monkeypatch
):
    import launcher.netplay.netplay as module

    context, _, _ = cd_context
    monkeypatch.setattr(module, "fsgs", context)
    context.amiga.cd_checksums_pending = True
    netplay = Mock()
    assert module.Netplay.host_game(netplay, "lobby.example", 2) is False
    netplay.game_warning.assert_called_once()
    netplay.create_game.assert_not_called()
