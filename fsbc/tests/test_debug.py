import fsbc.debug


def test_mypy():
    import fstd.mypy

    fstd.mypy.check_module(fsbc.debug.__name__)
