import sys

import fsboot
from fsbc.path import unicode_path
from fsbc.util import memoize

CSIDL_PERSONAL = 5
CSIDL_APPDATA = 26
CSIDL_PROFILE = 40
CSIDL_COMMON_DOCUMENTS = 46


@memoize
def get_user_name():
    return fsboot.user_name()


def get_documents_dir(create=False):
    return fsboot.documents_dir(create=create)


@memoize
def get_common_documents_dir():
    if sys.platform == "win32":
        path = fsboot.csidl_dir(CSIDL_COMMON_DOCUMENTS)
    else:
        raise NotImplementedError("Only for windows")
    path = unicode_path(path)
    return path


def get_home_dir():
    return fsboot.home_dir()


def get_data_dir(create=True):
    return fsboot.common_data_dir(create=create)
