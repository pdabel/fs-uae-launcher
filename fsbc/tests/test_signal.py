import fsbc.signal


def test_mypy():
    import fstd.mypy

    fstd.mypy.check_module(fsbc.signal.__name__)


def test_doctest():
    import doctest

    failure_count, test_count = doctest.testmod(fsbc.signal)
    assert failure_count == 0
