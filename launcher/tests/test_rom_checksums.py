import hashlib

from fsgs.amiga.amiga import Amiga
from launcher.launcher_config import LauncherConfig


def test_explicit_rom_checksum(tmp_path):
    rom = tmp_path / "kick.rom"
    rom.write_bytes(b"kickstart data")

    sha1 = LauncherConfig.checksum_explicit_rom(
        str(rom),
        str(tmp_path),
    )

    assert sha1 == hashlib.sha1(b"kickstart data").hexdigest()


def test_explicit_rom_checksum_relative_to_kickstart_dir(tmp_path):
    rom = tmp_path / "kick.rom"
    rom.write_bytes(b"kickstart data")

    sha1 = LauncherConfig.checksum_explicit_rom("kick.rom", str(tmp_path))

    assert sha1 == hashlib.sha1(b"kickstart data").hexdigest()


def test_explicit_rom_checksum_missing_file():
    assert (
        LauncherConfig.checksum_explicit_rom("missing.rom", "/missing") == ""
    )


def test_explicit_rom_checksum_url():
    url = "https://example.invalid/kick.rom"
    assert LauncherConfig.checksum_explicit_rom(url, "/missing") == url


def test_update_explicit_kickstarts(tmp_path):
    kickstart = tmp_path / "kick.rom"
    kickstart.write_bytes(b"main kickstart")
    ext = tmp_path / "ext.rom"
    ext.write_bytes(b"extension kickstart")
    config = {
        "amiga_model": "A1200",
        "kickstart_file": str(kickstart),
        "kickstart_ext_file": str(ext),
    }

    LauncherConfig.update_kickstart_in_config_dict(config)

    assert config["x_kickstart_file"] == str(kickstart)
    assert (
        config["x_kickstart_file_sha1"]
        == hashlib.sha1(b"main kickstart").hexdigest()
    )
    assert config["x_kickstart_ext_file"] == str(ext)
    assert (
        config["x_kickstart_ext_file_sha1"]
        == hashlib.sha1(b"extension kickstart").hexdigest()
    )


def test_update_internal_kickstart():
    config = {
        "amiga_model": "A1200",
        "kickstart_file": "internal",
        "kickstart_ext_file": "",
    }

    LauncherConfig.update_kickstart_in_config_dict(config)

    assert config["x_kickstart_file"] == "internal"
    assert config["x_kickstart_file_sha1"] == Amiga.INTERNAL_ROM_SHA1
    assert config["x_kickstart_ext_file"] == ""
    assert config["x_kickstart_ext_file_sha1"] == ""
