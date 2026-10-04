import fsbc.signal
import pytest


def test_mypy():
    pytest.skip()
    # import fstd.mypy
    # fstd.mypy.check_module(fsbc.signal.__name__)


def test_doctest():
    import doctest

    failure_count, test_count = doctest.testmod(fsbc.signal)
    assert failure_count == 0
