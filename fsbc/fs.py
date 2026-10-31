import os
import sys
import functools
import logging

# noinspection PyUnresolvedReferences
from fsbc.user import get_data_dir, get_home_dir
from fsbc.system import windows, macosx
from fsbc.util import memoize, Version, split_version, compare_versions


def cache(func):
    first_time = [True, None]

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if first_time[0]:
            first_time[1] = func(*args, **kwargs)
            first_time[0] = False
        return first_time[1]

    return wrapper


@cache
def get_lib_dir():
    lib_dir = os.environ.get("LIB_DIR", "")
    if lib_dir:
        return unicode_path(lib_dir)
    lib_dir = os.path.join(os.getcwd(), "lib")
    return lib_dir if os.path.exists(lib_dir) else ""


EXCEPTION = "EXCEPTION"


@cache
def get_app_id():
    return "fs-uae"


@memoize
def get_app_data_dir(app=None):
    path = os.path.join(get_data_dir(), app or get_app_id())
    os.makedirs(path, exist_ok=True)
    return path


@memoize
def get_app_config_dir(app=None):
    app = app or get_app_id()
    if windows:
        path = get_app_data_dir(app)
    elif macosx:
        path = os.path.join(get_home_dir(), "Library", "Preferences", app)
    else:
        path = os.path.join(
            os.environ.get(
                "XDG_CONFIG_HOME", os.path.join(get_home_dir(), ".config")
            ),
            app,
        )
    os.makedirs(path, exist_ok=True)
    return unicode_path(path)


def cause(exc, _cause):
    exc.__cause__ = _cause
    _cause.__traceback__ = sys.exc_info()[2]
    return exc


def encode_path(path):
    return path


def unicode_path(path):
    return path


def from_utf8_str(obj):
    return obj.decode("UTF-8") if isinstance(obj, bytes) else str(obj)


def to_utf8_str(obj):
    return obj


def utf8(obj):
    return unicode_safe(obj, "utf-8").encode("utf-8")


def utf8_safe(obj):
    return unicode_safe(obj, "utf-8").encode("utf-8")


def unicode_safe(obj, encoding="ASCII"):
    try:
        return str(obj)
    except Exception:
        logging.exception("Could not convert object to text")
        if isinstance(obj, bytes):
            return obj.decode(encoding, "replace")
        return "String returned from unicode_safe (problem logged)"


def normalize_path(path):
    path = os.path.normcase(os.path.normpath(path))
    return unicode_path(path)
