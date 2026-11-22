import atexit
import os
import shutil
import tempfile

# Keep every suite off the user's real FS-UAE directory. Without this,
# fsboot.base_dir() resolves to ~/FS-UAE (or Documents/FS-UAE), so tests
# read the user's Settings.ini, and a test that changes a setting writes
# it back there when Settings saves at exit. Tests that need their own
# base directory still set FS_UAE_BASE_DIR or patch fsboot.base_dir().
_base_dir = tempfile.mkdtemp(prefix="fs-uae-tests-")
os.environ["FS_UAE_BASE_DIR"] = _base_dir

# Registered before Settings registers its save, so it runs after it.
atexit.register(shutil.rmtree, _base_dir, ignore_errors=True)
