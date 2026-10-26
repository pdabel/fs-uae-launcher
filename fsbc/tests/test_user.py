import fsbc.user


def test_mypy():
    import fstd.mypy

    fstd.mypy.check_module(fsbc.user.__name__)


def test_doctest():
    import doctest

    failure_count, test_count = doctest.testmod(fsbc.user)
    assert failure_count == 0
