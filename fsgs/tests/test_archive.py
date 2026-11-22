import struct

from fsgs.archive import Archive


def crc16(data):
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def stored_lha(name, data):
    """A level-0 LHA archive holding one uncompressed (-lh0-) file."""
    name = name.encode("ascii")
    sizes = struct.pack("<IIIBBB", len(data), len(data), 0, 0x20, 0, len(name))
    header = b"-lh0-" + sizes + name + struct.pack("<H", crc16(data))
    return bytes([len(header), sum(header) & 0xFF]) + header + data + b"\0"


def test_lha_archives_are_read(tmp_path):
    # lhafile is a declared dependency. Without it fsgs.archive drops .lha
    # from the scanned extensions and opens .lha files as empty.
    path = tmp_path / "Game.lha"
    path.write_bytes(stored_lha("s/startup-sequence", b"echo hello\n"))
    assert ".lha" in Archive.extensions
    archive = Archive(str(path))
    member = f"{path}#/s/startup-sequence"
    assert archive.list_files() == [member]
    assert archive.open(member).read() == b"echo hello\n"
