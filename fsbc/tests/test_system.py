import fsbc.system


def test_mypy():
    import fstd.mypy

    fstd.mypy.check_module(fsbc.system.__name__)


def test_doctest():
    import doctest

    failure_count, test_count = doctest.testmod(fsbc.system)
    assert failure_count == 0
