import fsbc.seven_zip_file


def test_mypy():
    import fstd.mypy

    fstd.mypy.check_module(fsbc.seven_zip_file.__name__)
