import fsbc.resources


def test_doctest():
    import doctest

    failure_count, test_count = doctest.testmod(fsbc.resources)
    assert failure_count == 0
