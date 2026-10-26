import fsbc.user


def test_mypy():
    import fstd.mypy

    fstd.mypy.check_module(fsbc.user.__name__)
