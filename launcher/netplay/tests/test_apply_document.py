"""apply_document against the live launcher config."""

import pytest

from fsgs.context import fsgs
from launcher.launcher_config import LauncherConfig
from launcher.netplay.config_apply import accepted_keys, apply_document

MISSING = "9" * 40


@pytest.fixture(autouse=True)
def private_config(monkeypatch):
    # apply_document writes to the live config; keep it to this test.
    monkeypatch.setattr(fsgs.config, "values", dict(fsgs.config.values))


def snapshot(config, sync, checksum):
    return {
        "config_version": 1,
        "config": config,
        "keys": {"sync": sync, "checksum": checksum},
    }


def test_hash_is_over_the_documents_checksum_list(monkeypatch):
    # This launcher's own list would hash different keys: the document's
    # is the one every player uses.
    monkeypatch.setattr(LauncherConfig, "checksum_keys", ["accuracy"])
    doc = snapshot(
        {"amiga_model": "A1200", "chip_memory": "2048"},
        ["amiga_model", "chip_memory"],
        ["chip_memory", "amiga_model", "chip_memory"],
    )
    config_hash, missing = apply_document(doc)
    assert missing == {}
    assert fsgs.config.get("amiga_model") == "A1200"
    assert config_hash == LauncherConfig.checksum_config(
        doc["config"], doc["keys"]["checksum"]
    )


def test_missing_file_is_reported_and_changes_the_hash(monkeypatch):
    monkeypatch.setattr(fsgs.file, "find_by_sha1", lambda sha1: "")
    doc = snapshot(
        {"x_floppy_drive_0_sha1": MISSING},
        ["x_floppy_drive_0_sha1"],
        ["x_floppy_drive_0_sha1"],
    )
    config_hash, missing = apply_document(doc)
    assert missing == {"x_floppy_drive_0_sha1": MISSING}
    # The slot was cleared, so this player's hash differs from the host's.
    assert config_hash != LauncherConfig.checksum_config(
        doc["config"], doc["keys"]["checksum"]
    )
    assert fsgs.config.get("floppy_drive_0") == ""


def test_host_cannot_write_a_key_this_launcher_does_not_sync():
    # hard_drive_0 is a raw path, never synced: a host listing it in its
    # own key lists must not get to mount a player's filesystem.
    fsgs.config.set("hard_drive_0", "")
    doc = snapshot(
        {"amiga_model": "A1200", "hard_drive_0": "/"},
        ["amiga_model", "hard_drive_0"],
        ["amiga_model", "hard_drive_0"],
    )
    config_hash, missing = apply_document(doc)
    assert fsgs.config.get("hard_drive_0") == ""
    assert fsgs.config.get("amiga_model") == "A1200"
    # Left out, it hashes differently: the slot shows a mismatch.
    assert config_hash != LauncherConfig.checksum_config(
        doc["config"], doc["keys"]["checksum"]
    )


def test_unknown_key_is_a_mismatch_not_a_match():
    # A key a newer launcher added: not applied, so not hashed as if it
    # had been.
    doc = snapshot(
        {"x_some_future_option": "1"},
        ["x_some_future_option"],
        ["x_some_future_option"],
    )
    config_hash, _ = apply_document(doc)
    assert fsgs.config.get("x_some_future_option") != "1"
    assert config_hash != LauncherConfig.checksum_config(
        doc["config"], doc["keys"]["checksum"]
    )


def test_accepted_keys():
    local = {"amiga_model", "x_floppy_drive_0_sha1"}
    assert accepted_keys(
        [
            "amiga_model",
            "x_floppy_drive_0_sha1",
            # Past this launcher's own slots, but a media SHA-1 key.
            "x_floppy_image_19_sha1",
            "hard_drive_0",
            "floppy_drive_0",
            "x_some_future_option",
        ],
        local,
    ) == {"amiga_model", "x_floppy_drive_0_sha1", "x_floppy_image_19_sha1"}
