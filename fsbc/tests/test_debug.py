import fsbc.debug
import pytest


def test_mypy():
    pytest.skip()
    # import fstd.mypy
    # fstd.mypy.check_module(fsbc.debug.__name__)


def test_doctest():
    import doctest

    failure_count, test_count = doctest.testmod(fsbc.debug)
    assert failure_count == 0
