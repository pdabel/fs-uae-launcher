import ctypes
import getpass
import logging
import os
import subprocess
import sys
import time
from configparser import ConfigParser
from functools import lru_cache
from typing import Any, Dict, List, Optional

# The original argument list at boot time, before any modifications
_argv = []  # type: List[str]

# The current directory when the application was started
_cwd = os.getcwd()

# Key-value store
_values: Dict[str, str] = {}

# Found Plugin/Python code override directory
_plugin_code_override = False

logger = logging.getLogger("BOOT")
perf_counter_epoch = time.perf_counter()


def init() -> None:
    global _argv, _cwd
    _cwd = os.getcwd()
    _argv = sys.argv.copy()

    setup_python_path()
    print("sys.path =", sys.path)


def set(key: str, value: str) -> None:
    _values[key] = value


def get(key: str, default: str = "") -> str:
    return _values.get(key, default)


def setup_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter("[%(name)s] %(message)s")
    ch.setFormatter(formatter)
    root.addHandler(ch)


if "--logging" in sys.argv:
    setup_logging()
    sys.argv.remove("--logging")


@lru_cache()
def executable_dir() -> str:
    """Returns the directory containing the executable (or main script)."""
    logger.debug("executable_dir")
    logger.debug("sys.executable = %s", sys.executable)
    if "python" in os.path.basename(sys.executable):
        logger.debug("Using sys.argv[0] instead of python interpreter path")
        # We do not want the directory of the (installed) python
        # interpreter, but rather the main application script.
        logger.debug("sys.argv[0] = %s", repr(sys.argv[0]))
        path = os.path.dirname(os.path.abspath(sys.argv[0]))
        logger.debug("%s", repr(path))
    else:
        path = os.path.dirname(sys.executable)
    if not os.path.isabs(path):
        logger.warning(
            "WARNING: executable_dir %s is not absolute", repr(path)
        )
        print(
            f"WARNING: executable_dir {repr(path)} is not absolute",
            file=sys.stderr,
        )
    logger.debug("executable_dir = %s", repr(path))
    return path


@lru_cache()
def app_dir() -> str:
    """Returns the (absolute) directory containing the application.

    This is the same as the executable_dir, except for macOS where the
    directory containing the .app bundle is returned.
    """
    app_dir = executable_dir()
    if is_macos() and is_frozen():
        # Break out of .app/Contents/MacOS
        app_dir = os.path.normpath(os.path.join(app_dir, "..", "..", ".."))
    return app_dir


@lru_cache()
def plugin_dir() -> Optional[str]:
    """Returns the (absolute) directory containing the plugin (or None)."""
    plugin_dir = os.path.join(app_dir(), "..", "..")
    if os.path.exists(os.path.join(plugin_dir, "Plugin.ini")):
        return plugin_dir
    return None


if sys.platform == "win32":
    S_OK = 0
    CSIDL_DESKTOP = 0
    CSIDL_PERSONAL = 5
    CSIDL_APPDATA = 26
    CSIDL_MYPICTURES = 39
    CSIDL_PROFILE = 40
    CSIDL_COMMON_DOCUMENTS = 46
    from ctypes import windll
    from ctypes import wintypes

    _SHGetFolderPath = windll.shell32.SHGetFolderPathW
    _SHGetFolderPath.argtypes = [
        wintypes.HWND,
        ctypes.c_int,
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPCWSTR,
    ]

    def csidl_dir(csidl):
        path_buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        result = _SHGetFolderPath(0, csidl, 0, 0, path_buf)
        if result != S_OK:
            raise RuntimeError(
                f"Could not find common directory for CSIDL {csidl}"
            )
        return path_buf.value

    class WinPathsException(Exception):
        pass

    def err_unless_zero(result):
        if result == 0:
            return result
        else:
            raise WinPathsException(
                f'Failed to retrieve windows path: {result!s}'
            )

    _SHGetFolderPath.restype = err_unless_zero


@lru_cache()
def user_name() -> str:
    name = getpass.getuser()
    return name


@lru_cache()
def xdg_user_dir(name: str) -> Optional[str]:
    try:
        process = subprocess.Popen(
            ["xdg-user-dir", name], stdout=subprocess.PIPE
        )
        assert process.stdout is not None
        pathBytes = process.stdout.read().strip()
        path = pathBytes.decode("UTF-8")
        logger.debug("XDG user dir %s => %s", name, repr(path))
    except Exception:
        return None
    else:
        return path


@lru_cache()
def home_dir() -> str:
    if sys.platform == "win32":
        path = csidl_dir(CSIDL_PROFILE)
    else:
        path = os.path.expanduser("~")
    assert isinstance(path, str)
    return path


@lru_cache()
def documents_dir(create: bool = False) -> str:
    if sys.platform == "win32":
        path = csidl_dir(CSIDL_PERSONAL)
    elif sys.platform == "darwin":
        path = os.path.join(home_dir(), "Documents")
    else:
        path = xdg_user_dir("DOCUMENTS")
        if not path:
            path = home_dir()
    assert isinstance(path, str)
    if create and not os.path.isdir(path):
        os.makedirs(path)
    return path


def is_portable() -> bool:
    return portable_dir() is not None


@lru_cache()
def portable_dir() -> Optional[str]:
    path = executable_dir()
    last = ""
    while not last == path:
        portable_ini_path = os.path.join(path, "Portable.ini")
        logger.debug("Checking %s", repr(portable_ini_path))
        if os.path.exists(portable_ini_path):
            logger.debug("Detected portable dir: %s", repr(path))
            return path
        last = path
        path = os.path.dirname(path)
    logger.debug("No Portable.ini found in search path")
    return None


@lru_cache()
def common_data_dir(create: bool = False) -> str:
    if sys.platform == "win32":
        path = csidl_dir(CSIDL_APPDATA)
    elif sys.platform == "darwin":
        path = os.path.join(home_dir(), "Library", "Application Support")
    else:
        path = os.path.join(home_dir(), ".local", "share")
        path = os.environ.get("XDG_DATA_HOME", path)
    if create and not os.path.exists(path):
        os.makedirs(path)
    return path


@lru_cache()
def app_data_dir(app: str) -> str:
    return os.path.join(common_data_dir(), app)


@lru_cache()
def app_config_dir(app: str) -> str:
    if sys.platform == "win32":
        path = app_data_dir(app)
    elif sys.platform == "darwin":
        path = os.path.join(home_dir(), "Library", "Preferences", app)
    else:
        path = os.path.join(home_dir(), ".config")
        path = os.environ.get("XDG_CONFIG_HOME", path)
        path = os.path.join(path, app)
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


@lru_cache()
def custom_path(name: str) -> Optional[str]:
    app_names = ["fs-uae-launcher", "fs-uae"]
    for app_name in app_names:
        key_path = os.path.join(app_config_dir(app_name), name)
        logger.debug("Checking %s", repr(key_path))
        if os.path.exists(key_path):
            try:
                with open(key_path, "r", encoding="UTF-8") as f:
                    path = f.read().strip()
                    break
            except Exception as e:
                logger.debug("Error reading custom path %s", repr(e))
    else:
        return None
    path_lower = path.lower()
    if path_lower.startswith("$home/") or path_lower.startswith("$home\\"):
        path = os.path.join(home_dir(), path[6:])
    elif path_lower.startswith("~/") or path_lower.startswith("~\\"):
        path = os.path.join(home_dir(), path[2:])
    print(f"custom_path {name!r} -> {path!r}")
    logger.debug("custom_path %r -> %r", name, path)
    return path


def _getBaseDirectoryBeforeNormalization() -> str:
    path: Optional[str]
    logger.debug("Find base_dir")
    for arg in sys.argv[1:]:
        if arg.startswith("--base-dir="):
            path = arg[11:]
            path = os.path.abspath(path)
            logger.debug("Using base_dir via argv: %r", path)
            sys.argv.remove(arg)
            return path

    path = portable_dir()
    if path:
        config = ConfigParser(interpolation=None)
        config.read(os.path.join(path, "Portable.ini"), encoding="UTF-8")
        relative = config.get("launcher", "base_dir", fallback=".")
        return os.path.abspath(os.path.join(path, relative))

    logger.debug("Checking FS_UAE_BASE_DIR")
    path = os.environ.get("FS_UAE_BASE_DIR", "")
    if path:
        logger.debug("Using base_dir via FS_UAE_BASE_DIR: %r", path)
        return path

    path = custom_path("base-dir")
    if path:
        logger.debug("Using base_dir via custom path config: %r", path)
        return path

    if get("base_dir_name"):
        path = os.path.join(home_dir(), get("base_dir_name"))
    else:
        # Check new ~/FS-UAE directory first
        path = os.path.join(home_dir(), "FS-UAE")
        if os.path.exists(path):
            print("- using base_dir $HOME/FS-UAE")
        else:
            print("- using base_dir $DOCUMENTS/FS-UAE")
            # FS-UAE uses Documents/FS-UAE for legacy reasons
            path = os.path.join(documents_dir(), "FS-UAE")

    assert path is not None
    logger.debug("Using default base_dir %r", path)
    return path


@lru_cache()
def base_dir() -> str:
    path = _getBaseDirectoryBeforeNormalization()
    print("Using base_dir =", repr(path))
    # It is important to remove any trailing slash, etc. since the exact
    # base_dir is used for removing base_dir prefix from other paths.
    # Case normalization is important too, but that's done by FSGSDirectories.
    path = os.path.normpath(path)
    print("After normpath: base_dir =", repr(path))
    logger.debug("After normpath, base_dir = %r", path)
    if not os.path.exists(path):
        os.makedirs(path)
    return path


def getBaseDirectory() -> str:
    return base_dir()


@lru_cache()
def development() -> bool:
    # FIXME: Document option
    if "--development-mode=0" in sys.argv:
        return False
    result = os.path.exists(os.path.join(executable_dir(), "pyproject.toml"))
    logger.info("Development mode: %s", result)
    return result


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_macos() -> bool:
    return sys.platform == "darwin"


def setup_frozen_python_libs() -> None:
    return


def plugin_code_override() -> bool:
    return _plugin_code_override


# _python_dir: str


def setup_python_path_frozen() -> None:
    """Allow overriding code from Plugin/Python directory."""
    print("setup_python_path_frozen")


def setup_python_path() -> None:
    if is_frozen():
        setup_python_path_frozen()
