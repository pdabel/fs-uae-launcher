import fsbc.task


def test_mypy():
    import fstd.mypy

    fstd.mypy.check_module(fsbc.task.__name__)


def test_doctest():
    import doctest

    failure_count, test_count = doctest.testmod(fsbc.task)
    assert failure_count == 0
