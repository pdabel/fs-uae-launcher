import fsbc.init


def test_doctest():
    import doctest

    failure_count, test_count = doctest.testmod(fsbc.init)
    assert failure_count == 0
