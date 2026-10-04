import fsbc.util
import fstd.mypy
import doctest


def test_mypy():
    fstd.mypy.check_module(fsbc.util.__name__)


def test_doctest():
    failure_count, test_count = doctest.testmod(fsbc.util)
    assert failure_count == 0
