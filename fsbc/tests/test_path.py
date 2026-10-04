import fsbc.path


def test_mypy():
    import fstd.mypy

    fstd.mypy.check_module(fsbc.path.__name__)


def test_doctest():
    import doctest

    failure_count, test_count = doctest.testmod(fsbc.path)
    assert failure_count == 0
