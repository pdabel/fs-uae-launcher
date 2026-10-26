import fsbc.seven_zip_file


def test_mypy():
    import fstd.mypy

    fstd.mypy.check_module(fsbc.seven_zip_file.__name__)


def test_doctest():
    import doctest

    failure_count, test_count = doctest.testmod(fsbc.seven_zip_file)
    assert failure_count == 0
