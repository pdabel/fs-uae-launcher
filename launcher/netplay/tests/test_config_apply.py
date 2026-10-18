from types import SimpleNamespace

from fsgs.amiga.amiga import Amiga
from launcher.netplay.config_apply import file_keys, resolve_config

DEFAULT = SimpleNamespace(
    MAX_FLOPPY_DRIVES=4,
    MAX_FLOPPY_IMAGES=20,
    MAX_CDROM_DRIVES=4,
    MAX_CDROM_IMAGES=20,
    MAX_HARD_DRIVES=4,
)
FAST = SimpleNamespace(
    MAX_FLOPPY_DRIVES=4,
    MAX_FLOPPY_IMAGES=4,
    MAX_CDROM_DRIVES=0,
    MAX_CDROM_IMAGES=0,
    MAX_HARD_DRIVES=0,
)

KICK = "a" * 40
DISK = "b" * 40
FILES = {KICK: "/roms/kick.rom", DISK: "/disks/game.adf"}


def resolve(document, limits=DEFAULT):
    sync_keys = {"amiga_model", "x_kickstart_file_sha1"}
    sync_keys.add("x_kickstart_ext_file_sha1")
    sync_keys.update(file_keys(limits))
    return resolve_config(document, limits, sync_keys, FILES.get)


def test_file_keys_follow_limits():
    assert "x_floppy_image_5_sha1" in file_keys(DEFAULT)
    assert "x_floppy_image_5_sha1" not in file_keys(FAST)
    assert "x_cdrom_drive_0_sha1" not in file_keys(FAST)
    assert file_keys(FAST)["x_floppy_drive_3_sha1"] == "floppy_drive_3"


def test_plain_sync_key_is_set():
    assert resolve({"amiga_model": "A1200"}) == (
        [("amiga_model", "A1200")],
        {},
    )


def test_non_sync_key_is_ignored():
    assert resolve({"kickstart_file": "/etc/passwd"}) == ([], {})


def test_kickstart_found():
    updates, missing = resolve({"x_kickstart_file_sha1": KICK})
    assert updates == [
        ("kickstart_file", "/roms/kick.rom"),
        ("x_kickstart_file", "/roms/kick.rom"),
        ("x_kickstart_file_sha1", KICK),
    ]
    assert missing == {}


def test_internal_kickstart():
    sha1 = Amiga.INTERNAL_ROM_SHA1
    updates, _ = resolve({"x_kickstart_file_sha1": sha1})
    assert updates == [
        ("kickstart_file", "internal"),
        ("x_kickstart_file", "internal"),
        ("x_kickstart_file_sha1", sha1),
    ]


def test_kickstart_missing_leaves_config_alone():
    sha1 = "c" * 40
    assert resolve({"x_kickstart_file_sha1": sha1}) == (
        [],
        {"x_kickstart_file_sha1": sha1},
    )


def test_empty_ext_kickstart_clears_it():
    updates, missing = resolve({"x_kickstart_ext_file_sha1": ""})
    assert updates == [
        ("kickstart_ext_file", ""),
        ("x_kickstart_ext_file", ""),
        ("x_kickstart_ext_file_sha1", ""),
    ]
    assert missing == {}


def test_disk_found():
    assert resolve({"x_floppy_drive_0_sha1": DISK}) == (
        [
            ("floppy_drive_0", "/disks/game.adf"),
            ("x_floppy_drive_0_sha1", DISK),
        ],
        {},
    )


def test_disk_missing_clears_slot():
    sha1 = "d" * 40
    assert resolve({"x_floppy_drive_1_sha1": sha1}) == (
        [("floppy_drive_1", ""), ("x_floppy_drive_1_sha1", "")],
        {"x_floppy_drive_1_sha1": sha1},
    )


def test_empty_disk_clears_slot():
    assert resolve({"x_floppy_drive_2_sha1": ""}) == (
        [("floppy_drive_2", ""), ("x_floppy_drive_2_sha1", "")],
        {},
    )


def test_url_is_used_as_path():
    url = "https://example.com/game.adf"
    updates, missing = resolve({"x_floppy_image_0_sha1": url})
    assert updates == [
        ("floppy_image_0", url),
        ("x_floppy_image_0_sha1", url),
    ]
    assert missing == {}


def test_image_above_old_limit_is_resolved():
    # The stale-table bug: Fast at startup, Default now.
    updates, _ = resolve({"x_floppy_image_5_sha1": DISK}, DEFAULT)
    assert ("floppy_image_5", "/disks/game.adf") in updates


def test_whole_document_reports_every_missing_file():
    _, missing = resolve(
        {
            "amiga_model": "A500",
            "x_kickstart_file_sha1": "e" * 40,
            "x_floppy_drive_0_sha1": DISK,
            "x_floppy_drive_1_sha1": "f" * 40,
        }
    )
    assert missing == {
        "x_kickstart_file_sha1": "e" * 40,
        "x_floppy_drive_1_sha1": "f" * 40,
    }
