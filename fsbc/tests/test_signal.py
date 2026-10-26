import fsbc.signal
import pytest


def test_mypy():
    pytest.skip()


def test_doctest():
    import doctest

    failure_count, test_count = doctest.testmod(fsbc.signal)
    assert failure_count == 0
