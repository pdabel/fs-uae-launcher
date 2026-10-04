import fsbc.desktop


def test_mypy():
    import fstd.mypy

    fstd.mypy.check_module(fsbc.desktop.__name__)


def test_doctest():
    import doctest

    failure_count, test_count = doctest.testmod(fsbc.desktop)
    assert failure_count == 0
