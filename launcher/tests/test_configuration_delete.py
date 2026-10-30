import sqlite3

import pytest

from fsgs.Database import Database
from fsgs.filedatabase import FileDatabase
from launcher.configuration_scanner import ConfigurationScanner


@pytest.fixture
def indexed_configuration(tmp_path, monkeypatch):
    path = tmp_path / "Test.fs-uae"
    path.write_text("[fs-uae]\namiga_model = A500\n")
    database = Database(Database.SENTINEL)
    files = FileDatabase(FileDatabase.SENTINEL)
    database.connection = sqlite3.connect(":memory:")
    files.connection = sqlite3.connect(":memory:")
    database.connection.executescript(
        "CREATE TABLE game (id INTEGER PRIMARY KEY, uuid TEXT, path TEXT);"
        "CREATE TABLE search_term (game INTEGER, term TEXT);"
        "INSERT INTO game VALUES (1, NULL, '$/Test.fs-uae');"
        "INSERT INTO search_term VALUES (1, 'test');"
    )
    files.connection.executescript(
        "CREATE TABLE file (id INTEGER PRIMARY KEY, path TEXT, parent INTEGER);"
        "INSERT INTO file VALUES (1, '$/Test.fs-uae', NULL);"
    )
    monkeypatch.setattr("fsgs.BaseDatabase.use_debug_cursor", lambda: False)
    monkeypatch.setattr(
        "fsgs.FSGSDirectories.FSGSDirectories.get_base_dir",
        lambda: str(tmp_path),
    )
    monkeypatch.setattr(FileDatabase, "get_instance", lambda: files)
    try:
        yield path, database, files
    finally:
        database.connection.close()
        files.connection.close()


def test_delete_removes_only_configuration_and_its_indexes(
    indexed_configuration,
):
    path, database, files = indexed_configuration
    disk = path.with_suffix(".adf")
    disk.write_bytes(b"disk data")
    ConfigurationScanner.delete_configuration(database, str(path))
    assert not path.exists()
    assert disk.read_bytes() == b"disk data"
    assert database.connection.execute(
        "SELECT count(*) FROM game"
    ).fetchone() == (0,)
    assert database.connection.execute(
        "SELECT count(*) FROM search_term"
    ).fetchone() == (0,)
    assert files.connection.execute(
        "SELECT count(*) FROM file"
    ).fetchone() == (0,)


def test_permission_failure_keeps_file_and_indexes(
    indexed_configuration, monkeypatch
):
    path, database, files = indexed_configuration

    def denied(path):
        raise PermissionError("Permission denied")

    monkeypatch.setattr("launcher.configuration_scanner.os.unlink", denied)
    with pytest.raises(PermissionError):
        ConfigurationScanner.delete_configuration(database, str(path))
    assert path.exists()
    assert database.connection.execute(
        "SELECT count(*) FROM game"
    ).fetchone() == (1,)
    assert files.connection.execute(
        "SELECT count(*) FROM file"
    ).fetchone() == (1,)


def test_index_failure_does_not_remove_file(
    indexed_configuration, monkeypatch
):
    path, database, files = indexed_configuration

    def fail_index(**arguments):
        raise sqlite3.OperationalError("Database locked")

    monkeypatch.setattr(files, "delete_file", fail_index)
    with pytest.raises(sqlite3.OperationalError):
        ConfigurationScanner.delete_configuration(database, str(path))
    assert path.exists()
    assert database.connection.execute(
        "SELECT count(*) FROM game"
    ).fetchone() == (1,)


def test_database_entry_cannot_be_deleted(indexed_configuration):
    path, database, files = indexed_configuration
    database.connection.execute("UPDATE game SET uuid = 'database-game'")
    database.commit()
    with pytest.raises(ValueError, match="local configuration"):
        ConfigurationScanner.delete_configuration(database, str(path))
    assert path.exists()
    assert files.connection.execute(
        "SELECT count(*) FROM file"
    ).fetchone() == (1,)


def test_stale_missing_file_is_removed_from_indexes(indexed_configuration):
    path, database, files = indexed_configuration
    path.unlink()
    ConfigurationScanner.delete_configuration(database, str(path))
    assert database.connection.execute(
        "SELECT count(*) FROM game"
    ).fetchone() == (0,)
    assert files.connection.execute(
        "SELECT count(*) FROM file"
    ).fetchone() == (0,)


def test_non_configuration_file_is_rejected(indexed_configuration):
    path, database, _ = indexed_configuration
    with pytest.raises(ValueError, match=".fs-uae"):
        ConfigurationScanner.delete_configuration(
            database, str(path.with_suffix(".adf"))
        )
    assert path.exists()


def test_delete_symbolic_link_does_not_remove_its_target(
    indexed_configuration,
):
    path, database, _ = indexed_configuration
    target = path.with_name("Original.fs-uae")
    path.rename(target)
    path.symlink_to(target)
    ConfigurationScanner.delete_configuration(database, str(path))
    assert not path.is_symlink()
    assert target.read_text() == "[fs-uae]\namiga_model = A500\n"
