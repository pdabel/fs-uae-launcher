import fsbc.util
import fstd.mypy
import doctest
import pytest

from amitools.util.ByteSize import to_byte_size_str
from oyoyo.cmdhandler import NoSuchCommandError


def test_mypy():
    fstd.mypy.check_module(fsbc.util.__name__)


def test_doctest():
    failure_count, test_count = doctest.testmod(fsbc.util)
    assert failure_count == 0


@pytest.mark.parametrize(
    "size,kibi,expected",
    [(0, True, "  0Bi"), (1024, True, "1.0Ki"),
     (1000, False, "1.0K"), (10240, True, " 10Ki"),
     (1024**5, True, "NaNBi")],
)
def test_byte_size_formatting(size, kibi, expected):
    assert to_byte_size_str(size, kibi) == expected


def test_command_error_string():
    assert str(NoSuchCommandError(["server", "join"])) == (
        'No such command "server.join"'
    )
