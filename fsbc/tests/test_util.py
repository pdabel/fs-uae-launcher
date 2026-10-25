import fsbc.util
import fstd.mypy
import doctest

from oyoyo.cmdhandler import NoSuchCommandError


def test_mypy():
    fstd.mypy.check_module(fsbc.util.__name__)


def test_doctest():
    failure_count, test_count = doctest.testmod(fsbc.util)
    assert failure_count == 0


def test_command_error_string():
    assert str(NoSuchCommandError(["server", "join"])) == (
        'No such command "server.join"'
    )
