import fsbc.system


def test_mypy():
    import fstd.mypy

    fstd.mypy.check_module(fsbc.system.__name__)
