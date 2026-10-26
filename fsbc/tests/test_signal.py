import fsbc.signal


def test_mypy():
    import fstd.mypy

    fstd.mypy.check_module(fsbc.signal.__name__)
