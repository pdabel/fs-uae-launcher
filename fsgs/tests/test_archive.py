import struct
from io import BytesIO
from zipfile import ZipFile

import pytest

from fsgs.archive import Archive, ByteSwapWordsFilter


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


@pytest.mark.parametrize(
    "data, expected",
    [
        (b"ABCDEF", b"BADCFE"),
        (b"ABCDEFG", b"BADCFEG"),
    ],
)
@pytest.mark.parametrize("read_size", [1, 2, 3, -1])
def test_word_swap_respects_read_sizes_and_eof(data, expected, read_size):
    stream = ByteSwapWordsFilter(BytesIO(data))
    chunks = []
    while True:
        chunk = stream.read(read_size)
        if not chunk:
            break
        if read_size >= 0:
            assert len(chunk) <= read_size
        chunks.append(chunk)
    assert b"".join(chunks) == expected
    assert stream.read() == b""


def test_word_swap_zero_and_mixed_reads():
    source = BytesIO(b"ABCDEFG")
    stream = ByteSwapWordsFilter(source)
    assert stream.read(0) == b""
    assert source.tell() == 0
    assert stream.read(1) == b"B"
    assert stream.read(3) == b"ADC"
    assert stream.read(0) == b""
    assert stream.read(2) == b"FE"
    assert stream.read() == b"G"
    assert stream.read(1) == b""


def test_word_swap_handles_short_underlying_reads():
    class ShortReads(BytesIO):
        def read(self, n=-1):
            return super().read(1 if n < 0 else min(n, 1))

    stream = ByteSwapWordsFilter(ShortReads(b"ABCDEFG"))
    assert stream.read(3) == b"BAD"
    assert stream.read() == b"CFEG"


@pytest.mark.parametrize("extension", [".zip", ".gz", ".7z", ".lha"])
def test_archive_looking_directory_is_not_an_archive(tmp_path, extension):
    directory = tmp_path / f"games{extension}"
    directory.mkdir()
    media = directory / "disk.adf"
    media.write_bytes(b"floppy")
    archive = Archive(str(media))
    assert archive.path == str(media)
    assert archive.sub_path == ""
    with archive.open(str(media)) as stream:
        assert stream.read() == b"floppy"


def test_real_archive_inside_archive_looking_directory(tmp_path):
    directory = tmp_path / "games.zip"
    directory.mkdir()
    path = directory / "real.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("disk.adf", b"floppy")
    member = f"{path}/disk.adf"
    archive = Archive(member)
    assert archive.path == str(path)
    assert archive.sub_path == "disk.adf"
    with archive.open(member) as stream:
        assert stream.read() == b"floppy"
