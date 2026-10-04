import fsbc.resources
import pytest


def test_mypy():
    pytest.skip()
    # import fstd.mypy
    # fstd.mypy.check_module(fsbc.Resources.__name__)


def test_doctest():
    import doctest

    failure_count, test_count = doctest.testmod(fsbc.resources)
    assert failure_count == 0
