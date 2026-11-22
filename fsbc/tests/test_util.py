import fsbc.util
import doctest


def test_doctest():
    failure_count, test_count = doctest.testmod(fsbc.util)
    assert failure_count == 0
