import fsbc.path


def test_mypy():
    import fstd.mypy

    fstd.mypy.check_module(fsbc.path.__name__)
