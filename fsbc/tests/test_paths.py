import fsbc.paths


def test_doctest():
    import doctest

    failure_count, test_count = doctest.testmod(fsbc.paths)
    assert failure_count == 0
