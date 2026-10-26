import fsbc.logging


def test_doctest():
    import doctest

    failure_count, test_count = doctest.testmod(fsbc.logging)
    assert failure_count == 0
