import shutil
import sqlite3
import stat
import sys
from configparser import ConfigParser
from contextlib import closing

import pytest

from launcher.portable import PortableModeChange


def make_change(tmp_path, enabled=True):
    source = tmp_path / "original"
    source.mkdir()
    launcher = tmp_path / "launcher"
    launcher.mkdir()
    return PortableModeChange(
        source,
        launcher / "Amiga Data",
        launcher / "Portable.ini",
        enabled,
        tmp_path / "preferences" / "base-dir",
    )


def test_enable_copies_data_and_writes_relative_marker(tmp_path):
    change = make_change(tmp_path)
    (change.source / "Kickstarts").mkdir()
    (change.source / "Kickstarts" / "example.rom").write_bytes(b"rom")
    change.apply()
    assert (
        change.source / "Kickstarts" / "example.rom"
    ).read_bytes() == b"rom"
    assert (
        change.destination / "Kickstarts" / "example.rom"
    ).read_bytes() == b"rom"
    config = ConfigParser()
    config.read(change.marker)
    assert config["launcher"]["base_dir"] == "Amiga Data"
    assert not change.normal_path.exists()


def test_disable_preserves_marker_backup_and_sets_normal_folder(tmp_path):
    change = make_change(tmp_path, enabled=False)
    change.marker.write_text("[directories]\nfloppies_dir = Disks\n")
    change.apply()
    assert not change.marker.exists()
    backups = list(change.marker.parent.glob("Portable.ini.disabled-*"))
    assert len(backups) == 1
    assert "floppies_dir" in backups[0].read_text()
    assert change.normal_path.read_text() == str(change.destination)


@pytest.mark.parametrize("destination", ["occupied", "child", "parent"])
def test_unsafe_destination_is_rejected(tmp_path, destination):
    change = make_change(tmp_path)
    if destination == "occupied":
        change.destination.mkdir()
        (change.destination / "keep").write_text("existing")
    elif destination == "child":
        change.destination = change.source / "child"
    else:
        change.destination = change.source.parent
    with pytest.raises(OSError):
        change.apply()
    assert not change.marker.exists()


def test_failed_copy_does_not_change_startup_or_original(
    tmp_path, monkeypatch
):
    change = make_change(tmp_path)
    (change.source / "keep").write_text("original")

    def fail_copy(*arguments):
        raise OSError("Disk full")

    monkeypatch.setattr(change, "copy_file", fail_copy)
    with pytest.raises(OSError, match="Disk full"):
        change.apply()
    assert (change.source / "keep").read_text() == "original"
    assert not change.marker.exists()
    assert not change.destination.exists()


def test_sqlite_backup_includes_wal_data(tmp_path):
    change = make_change(tmp_path)
    databases = change.source / "Data" / "Databases"
    databases.mkdir(parents=True)
    with closing(sqlite3.connect(databases / "Files.sqlite")) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE example (name TEXT)")
        connection.execute("INSERT INTO example VALUES ('preserved')")
        connection.commit()
        change.apply()
    with closing(
        sqlite3.connect(
            change.destination / "Data" / "Databases" / "Files.sqlite"
        )
    ) as backup:
        assert backup.execute("SELECT name FROM example").fetchone() == (
            "preserved",
        )
    assert not (
        change.destination / "Data" / "Databases" / "Files.sqlite-wal"
    ).exists()


def test_preferences_inside_root_are_rebased(tmp_path):
    change = make_change(tmp_path)
    data = change.source / "Data"
    data.mkdir()
    (data / "Settings.ini").write_text(
        "[settings]\nsearch_path = "
        + str(change.source / "Floppies")
        + ";-/external;-/unrelated\nlast_rom_dir = "
        + str(change.source / "Kickstarts")
        + "\nkickstarts_dir_mtime = 123\n"
    )
    change.apply()
    config = ConfigParser()
    config.read(change.destination / "Data" / "Settings.ini")
    assert config["settings"]["last_rom_dir"] == ""
    assert (
        config["settings"]["search_path"]
        == "$BASE/Floppies;-/external;-/unrelated"
    )
    assert config["settings"]["kickstarts_dir_mtime"] == ""


def test_internal_configuration_paths_become_portable(tmp_path):
    change = make_change(tmp_path)
    configurations = change.source / "Configurations"
    configurations.mkdir()
    original = (
        "[fs-uae]\nfloppy_drive_0 = "
        + str(change.source / "Floppies" / "game.adf")
        + "\nhard_drive_0 = /external/hard-disk\n"
    )
    (configurations / "Game.fs-uae").write_text(original)
    change.apply()
    config = ConfigParser()
    config.read(change.destination / "Configurations" / "Game.fs-uae")
    assert config["fs-uae"]["floppy_drive_0"] == "$BASE/Floppies/game.adf"
    assert config["fs-uae"]["hard_drive_0"] == "/external/hard-disk"
    assert (configurations / "Game.fs-uae").read_text() == original


def test_relative_scan_paths_follow_current_root(monkeypatch):
    from fsbc.paths import Paths
    from fsgs.FSGSDirectories import FSGSDirectories
    from launcher.launcher_settings import LauncherSettings
    from launcher.settings.scan_paths_group import ScanPathsGroup

    monkeypatch.setattr(Paths, "get_base_dir", lambda: "/relocated")
    monkeypatch.setattr(
        FSGSDirectories, "get_default_search_path", lambda: ["/relocated"]
    )
    monkeypatch.setattr(
        FSGSDirectories,
        "get_configurations_dir",
        lambda: "/relocated/Configurations",
    )
    monkeypatch.setattr(
        FSGSDirectories, "get_kickstarts_dir", lambda: "/relocated/Kickstarts"
    )
    monkeypatch.setattr(
        LauncherSettings, "get", lambda key: "-$BASE/;$BASE/Floppies"
    )
    assert ScanPathsGroup.get_search_path() == [
        "/relocated/Floppies",
        "/relocated/Configurations",
        "/relocated/Kickstarts",
    ]


def test_portable_folder_survives_whole_bundle_relocation(
    tmp_path, monkeypatch
):
    import fsboot

    change = make_change(tmp_path)
    change.apply()
    relocated = tmp_path / "relocated launcher"
    shutil.move(change.marker.parent, relocated)
    monkeypatch.setattr(sys, "argv", ["fs-uae-launcher"])
    monkeypatch.setattr(fsboot, "executable_dir", lambda: str(relocated))
    monkeypatch.setattr(
        fsboot, "portable_dir", fsboot.portable_dir.__wrapped__
    )
    assert fsboot.is_portable()
    assert fsboot._getBaseDirectoryBeforeNormalization() == str(
        relocated / "Amiga Data"
    )


def test_normal_mode_survives_cold_start(tmp_path, monkeypatch):
    import fsboot

    change = make_change(tmp_path, enabled=False)
    change.marker.write_text("")
    change.apply()
    monkeypatch.setattr(sys, "argv", ["fs-uae-launcher"])
    monkeypatch.delenv("FS_UAE_BASE_DIR", raising=False)
    monkeypatch.setattr(
        fsboot, "executable_dir", lambda: str(change.marker.parent)
    )
    monkeypatch.setattr(
        fsboot, "portable_dir", fsboot.portable_dir.__wrapped__
    )
    monkeypatch.setattr(
        fsboot, "app_config_dir", lambda name: str(change.normal_path.parent)
    )
    monkeypatch.setattr(fsboot, "custom_path", fsboot.custom_path.__wrapped__)
    assert not fsboot.is_portable()
    assert fsboot._getBaseDirectoryBeforeNormalization() == str(
        change.destination
    )


def test_enable_in_place_is_rejected_without_changing_originals(tmp_path):
    change = make_change(tmp_path)
    change.destination = change.source
    (change.source / "keep").write_text("original")
    with pytest.raises(OSError, match="new empty folder"):
        change.apply()
    assert (change.source / "keep").read_text() == "original"
    assert not change.marker.exists()


def test_startup_write_failure_keeps_completed_copy(tmp_path, monkeypatch):
    import launcher.portable

    change = make_change(tmp_path)
    change.marker.write_text("[launcher]\nbase_dir = old\n")
    original_marker = change.marker.read_bytes()

    def fail_write(*arguments):
        raise OSError("Read-only installation")

    monkeypatch.setattr(launcher.portable, "write_atomic", fail_write)
    with pytest.raises(OSError, match="Read-only installation"):
        change.apply()
    assert change.marker.read_bytes() == original_marker
    assert change.source.is_dir()
    assert change.destination.is_dir()


def test_external_linked_settings_are_not_modified(tmp_path):
    change = make_change(tmp_path)
    external = tmp_path / "external settings"
    external.mkdir()
    original = (
        "[settings]\nlast_rom_dir = "
        + str(change.source / "Kickstarts")
        + "\n"
    )
    (external / "Settings.ini").write_text(original)
    (change.source / "Data").symlink_to(external, target_is_directory=True)
    change.apply()
    assert (external / "Settings.ini").read_text() == original


def test_custom_portable_folder_mappings_are_preserved(tmp_path):
    change = make_change(tmp_path)
    custom_data = change.source / "Custom Data"
    custom_data.mkdir()
    (custom_data / "Settings.ini").write_text(
        "[settings]\nsearch_path = " + str(change.source / "Disks") + "\n"
    )
    (change.source / "Portable.ini").write_text(
        "[directories]\ndata_dir = "
        + str(custom_data)
        + "\nfloppies_dir = Disks\n"
    )
    change.apply()
    config = ConfigParser()
    config.read(change.destination / "Portable.ini")
    assert config["directories"]["data_dir"] == "Custom Data"
    assert config["directories"]["floppies_dir"] == "Disks"
    settings = ConfigParser()
    settings.read(change.destination / "Custom Data" / "Settings.ini")
    assert settings["settings"]["search_path"] == "$BASE/Disks"


def test_removed_relative_root_can_be_added_again(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    import fsui
    from fsbc.paths import Paths
    from fsgs.FSGSDirectories import FSGSDirectories
    from launcher.launcher_settings import LauncherSettings
    from launcher.settings.scan_paths_group import ScanPathsGroup

    settings = {"search_path": ""}
    monkeypatch.setattr(Paths, "get_base_dir", lambda: "/relocated")
    monkeypatch.setattr(FSGSDirectories, "get_base_dir", lambda: "/relocated")
    monkeypatch.setattr(
        FSGSDirectories, "get_default_search_path", lambda: ["/relocated"]
    )
    monkeypatch.setattr(LauncherSettings, "get", settings.get)
    monkeypatch.setattr(LauncherSettings, "set", settings.__setitem__)
    monkeypatch.setattr(
        fsui, "pick_directory", lambda **arguments: "/relocated"
    )
    group = SimpleNamespace(
        list_view=Mock(),
        get_window=lambda: None,
    )
    group.list_view.get_item.return_value = "/relocated"
    ScanPathsGroup.on_remove_button(group)
    assert settings["search_path"] == "-$BASE/"
    ScanPathsGroup.on_add_button(group)
    assert settings["search_path"] == ""


def test_copy_race_preserves_new_destination_files(tmp_path):
    change = make_change(tmp_path)
    (change.source / "keep").write_text("source")

    def occupy_destination(message):
        change.destination.mkdir(exist_ok=True)
        (change.destination / "keep").write_text("other process")

    with pytest.raises(OSError):
        change.apply(occupy_destination)
    assert (change.destination / "keep").read_text() == "other process"
    assert not change.marker.exists()
    assert not list(change.destination.parent.glob(".portable-copy-*"))


def test_failed_copy_does_not_remove_concurrently_created_destination(
    tmp_path, monkeypatch
):
    change = make_change(tmp_path)
    (change.source / "keep").write_text("source")

    def fail_copy(*args):
        change.destination.mkdir()
        (change.destination / "keep").write_text("unrelated")
        raise OSError("Disk full")

    monkeypatch.setattr(change, "copy_file", fail_copy)
    with pytest.raises(OSError, match="Disk full"):
        change.apply()
    assert (change.destination / "keep").read_text() == "unrelated"


def test_disable_in_place_rejects_directory_mappings(tmp_path):
    change = make_change(tmp_path, enabled=False)
    change.destination = change.source
    change.marker = change.source / "Portable.ini"
    change.marker.write_text("[directories]\ndata_dir = Custom Data\n")
    with pytest.raises(OSError, match="directory mappings"):
        change.apply()
    assert change.marker.is_file()
    assert not change.normal_path.exists()


def test_symlinks_keep_internal_and_external_targets(tmp_path):
    change = make_change(tmp_path)
    external = tmp_path / "Shared"
    external.mkdir()
    (change.source / "Disks").mkdir()
    (change.source / "Internal").symlink_to("Disks", target_is_directory=True)
    (change.source / "External").symlink_to(
        "../Shared", target_is_directory=True
    )
    change.apply()
    assert (change.destination / "External").resolve() == external
    assert (change.destination / "Internal").readlink().as_posix() == "Disks"
    assert (
        change.destination / "Internal"
    ).resolve() == change.destination / "Disks"


def test_sqlite_backup_preserves_private_permissions(tmp_path):
    change = make_change(tmp_path)
    database = change.source / "Data" / "Databases" / "NetplayHistory.sqlite"
    database.parent.mkdir(parents=True)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TABLE history (command TEXT)")
    database.chmod(0o600)
    change.apply()
    copied = change.destination / database.relative_to(change.source)
    assert stat.S_IMODE(copied.stat().st_mode) == 0o600


def test_migration_accepts_duplicate_configuration_keys_and_sections(tmp_path):
    change = make_change(tmp_path)
    (change.source / "Game.fs-uae").write_text(
        "[fs-uae]\nchip_memory = 512\nchip_memory = 1024\n"
        "[fs-uae]\nfloppy_drive_0 = " + str(change.source / "game.adf") + "\n"
    )
    change.apply()
    config = ConfigParser()
    config.read(change.destination / "Game.fs-uae")
    assert config["fs-uae"]["chip_memory"] == "1024"
    assert config["fs-uae"]["floppy_drive_0"] == "$BASE/game.adf"


def test_external_relative_directory_mapping_is_preserved(tmp_path):
    change = make_change(tmp_path)
    (change.source / "Portable.ini").write_text(
        "[directories]\nfloppies_dir = ../Shared Disks\n"
    )
    change.apply()
    config = ConfigParser()
    config.read(change.destination / "Portable.ini")
    assert (
        config["directories"]["floppies_dir"]
        == (tmp_path / "Shared Disks").as_posix()
    )


def test_migrated_config_preference_survives_relocation(tmp_path, monkeypatch):
    from fsbc.paths import Paths

    change = make_change(tmp_path)
    data = change.source / "Data"
    data.mkdir()
    (data / "Settings.ini").write_text(
        "[settings]\nconfig_path = "
        + str(change.source / "Game.fs-uae")
        + "\n"
    )
    (change.source / "Game.fs-uae").write_text(
        "[fs-uae]\namiga_model = A500\n"
    )
    change.apply()
    relocated = tmp_path / "Moved"
    shutil.move(change.destination, relocated)
    settings = ConfigParser()
    settings.read(relocated / "Data" / "Settings.ini")
    stored = settings["settings"]["config_path"]
    assert stored == "$BASE/Game.fs-uae"
    monkeypatch.setattr(Paths, "get_base_dir", lambda: str(relocated))
    assert Paths.expand_path(stored) == str(relocated / "Game.fs-uae")


def test_path_rebasing_normalizes_separators_without_changing_nonpaths(
    tmp_path,
):
    from launcher.portable import internal_path

    change = make_change(tmp_path)
    assert (
        internal_path(
            str(change.source / "Disks").replace("/", "\\"), change.source
        ).as_posix()
        == "Disks"
    )
    assert internal_path("not a path", change.source) is None


def test_scan_paths_compare_both_separator_forms(monkeypatch):
    from fsbc.paths import Paths
    from fsgs.FSGSDirectories import FSGSDirectories
    from launcher.launcher_settings import LauncherSettings
    from launcher.settings.scan_paths_group import ScanPathsGroup

    monkeypatch.setattr(Paths, "get_base_dir", lambda: "/relocated")
    monkeypatch.setattr(
        FSGSDirectories,
        "get_default_search_path",
        lambda: ["\\relocated", "\\relocated\\Disks"],
    )
    monkeypatch.setattr(
        FSGSDirectories,
        "get_configurations_dir",
        lambda: "/relocated/Configurations",
    )
    monkeypatch.setattr(
        FSGSDirectories, "get_kickstarts_dir", lambda: "/relocated/Kickstarts"
    )
    monkeypatch.setattr(
        LauncherSettings, "get", lambda key: "-$BASE/;$BASE/Disks"
    )
    assert ScanPathsGroup.get_search_path() == [
        "/relocated/Disks",
        "/relocated/Configurations",
        "/relocated/Kickstarts",
    ]


def test_loading_portable_configuration_keeps_relative_preference(
    tmp_path, monkeypatch
):
    import fsboot
    from fsbc.paths import Paths
    from launcher.launcher_config import LauncherConfig
    from launcher.launcher_settings import LauncherSettings

    path = tmp_path / "Game.fs-uae"
    path.write_text("[fs-uae]\namiga_model = A500\n")
    settings = {}
    monkeypatch.setattr(fsboot, "is_portable", lambda: True)
    monkeypatch.setattr(
        Paths,
        "get_base_dir",
        lambda slash=False: str(tmp_path) + ("/" if slash else ""),
    )
    monkeypatch.setattr(
        LauncherSettings, "get", lambda key: settings.get(key, "")
    )
    monkeypatch.setattr(LauncherSettings, "set", settings.__setitem__)
    monkeypatch.setattr(LauncherConfig, "load", lambda config: None)
    monkeypatch.setattr(LauncherConfig, "get", lambda key, default="": default)
    monkeypatch.setattr(LauncherConfig, "set", lambda key, value: None)
    assert LauncherConfig._load_file("$BASE/Game.fs-uae", "")
    assert settings["config_path"] == "$BASE/Game.fs-uae"
    assert Paths.expand_path("$CONFIG/disks/game.adf") == str(
        tmp_path / "disks" / "game.adf"
    )
