import fsbc.seven_zip_file
import pytest


def test_mypy():
    pytest.skip()


def test_doctest():
    import doctest

    failure_count, test_count = doctest.testmod(fsbc.seven_zip_file)
    assert failure_count == 0
