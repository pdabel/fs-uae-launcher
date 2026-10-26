import fsbc.paths
import pytest


def test_mypy():
    pytest.skip()


def test_doctest():
    import doctest

    failure_count, test_count = doctest.testmod(fsbc.paths)
    assert failure_count == 0
