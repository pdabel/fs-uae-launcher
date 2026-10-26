import fsbc.task


def test_mypy():
    import fstd.mypy

    fstd.mypy.check_module(fsbc.task.__name__)
