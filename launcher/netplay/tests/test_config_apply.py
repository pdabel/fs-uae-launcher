from fsgs.amiga.amiga import Amiga
from launcher.netplay.config_apply import media_path_key, resolve_config

KICK = "a" * 40
DISK = "b" * 40
FILES = {KICK: "/roms/kick.rom", DISK: "/disks/game.adf"}

SYNC_KEYS = {
    "amiga_model",
    "x_kickstart_file_sha1",
    "x_kickstart_ext_file_sha1",
    "x_floppy_drive_0_sha1",
    "x_floppy_drive_1_sha1",
    "x_floppy_drive_2_sha1",
    "x_floppy_image_0_sha1",
    "x_floppy_image_19_sha1",
    "x_cdrom_drive_0_sha1",
}


def resolve(document, sync_keys=SYNC_KEYS):
    return resolve_config(document, sync_keys, FILES.get)


def test_media_path_key():
    assert media_path_key("x_floppy_drive_3_sha1") == "floppy_drive_3"
    assert media_path_key("x_floppy_image_19_sha1") == "floppy_image_19"
    assert media_path_key("x_cdrom_image_0_sha1") == "cdrom_image_0"
    assert media_path_key("x_hard_drive_2_sha1") == "hard_drive_2"
    assert media_path_key("x_kickstart_file_sha1") is None
    assert media_path_key("floppy_drive_0") is None
    assert media_path_key("x_floppy_drive_sha1") is None


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


def test_empty_kickstart_clears_it():
    updates, missing = resolve({"x_kickstart_file_sha1": ""})
    assert updates == [
        ("kickstart_file", ""),
        ("x_kickstart_file", ""),
        ("x_kickstart_file_sha1", ""),
    ]
    assert missing == {}


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


def test_media_slot_is_resolved_whatever_the_local_limits():
    # Matched by name: a slot beyond what Fast mode would list (images past
    # 4, any CD-ROM) still resolves to a path when the document has it.
    for key, path_key in [
        ("x_floppy_image_19_sha1", "floppy_image_19"),
        ("x_cdrom_drive_0_sha1", "cdrom_drive_0"),
    ]:
        updates, _ = resolve({key: DISK})
        assert (path_key, "/disks/game.adf") in updates


def test_document_sync_keys_decide_what_is_applied():
    document = {"amiga_model": "A1200", "chip_memory": "2048"}
    assert resolve(document, {"amiga_model"}) == (
        [("amiga_model", "A1200")],
        {},
    )
    updates, _ = resolve(document, {"amiga_model", "chip_memory"})
    assert ("chip_memory", "2048") in updates


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
