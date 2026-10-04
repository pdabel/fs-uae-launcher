import fsbc.paths
import pytest


def test_mypy():
    pytest.skip()
    # import fstd.mypy
    # fstd.mypy.check_module(fsbc.Paths.__name__)


def test_doctest():
    import doctest

    failure_count, test_count = doctest.testmod(fsbc.paths)
    assert failure_count == 0
