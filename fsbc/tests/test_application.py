import fsbc.application


def test_doctest():
    import doctest

    failure_count, test_count = doctest.testmod(fsbc.application)
    assert failure_count == 0
