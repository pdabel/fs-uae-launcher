import os

import pytest

import fspy.zipfile


def test_latin1_name():
    zf = fspy.zipfile.ZipFile(
        os.path.join(os.path.dirname(__file__), "zipfile", "iso-8859-1.zip"),
        "r",
    )
    assert zf.namelist() == ["F\xf8rde"]
    zf.read("F\xf8rde")
    pytest.raises(KeyError, zf.read, "Forde")
    zf.getinfo("F\xf8rde")
    zf.close()


def test_utf8_name():
    zf = fspy.zipfile.ZipFile(
        os.path.join(os.path.dirname(__file__), "zipfile", "utf-8.zip"), "r"
    )
    assert zf.namelist() == ["F\xf8rde"]
    zf.read("F\xf8rde")
    pytest.raises(KeyError, zf.read, "Forde")
    zf.getinfo("F\xf8rde")
    zf.close()
