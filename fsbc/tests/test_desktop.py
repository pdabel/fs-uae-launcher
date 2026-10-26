import fsbc.desktop


def test_mypy():
    import fstd.mypy

    fstd.mypy.check_module(fsbc.desktop.__name__)
