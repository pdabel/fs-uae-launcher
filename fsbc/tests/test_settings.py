import os
import tempfile
import fsbc.settings


def test_load_save():
    fd, path = tempfile.mkstemp()
    os.close(fd)
    fsbc.settings.set_path(path)
    fsbc.settings.load()

    fsbc.settings.set("Key-å", "Value-å")
    fsbc.settings.save()
    fsbc.settings.unload()

    fsbc.settings.load()

    value = fsbc.settings.get("Key-å")
    assert value == "Value-å"
    fsbc.settings.unload()


def test_mypy():
    import fstd.mypy

    fstd.mypy.check_module(fsbc.settings.__name__)
