# import os
import zipfile
import tempfile

# noinspection PyUnresolvedReferences
from typing import IO, Dict, Optional


_archive = None  # type: Optional[zipfile.ZipFile]
_temp = {}  # type: Dict[str, str]


def app_name() -> str:
    raise NotImplementedError()


def archive() -> zipfile.ZipFile:
    global _archive
    if _archive is None:
        _archive = zipfile.ZipFile(app_name() + ".dat", "r")
    return _archive


def reset() -> None:
    global _archive
    _archive = None


def path_no_extract(name: str) -> str:
    return name


def path(name: str) -> str:
    try:
        return _temp[name]
    except KeyError:
        pass
    try:
        return path_no_extract(name)
    except LookupError:
        s = stream(name)
        fd, p = tempfile.mkstemp(suffix=name)
        with open(fd, "wb") as f:
            f.write(s.read())
        _temp[name] = p
        return p

    # if p is None:
    #     raise LookupError(name)
    # return p


# def stream(name: str, mode: str="rb") -> IO[bytes]:
def stream(name: str) -> IO[bytes]:
    # archive().read()
    return archive().open(name)
