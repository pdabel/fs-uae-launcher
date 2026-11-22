import io

from fsbc.resources import Resources


def test_read_returns_the_bytes_and_closes_the_stream(monkeypatch):
    stream = io.BytesIO(b"data")
    monkeypatch.setattr(Resources, "stream", lambda self, resource: stream)
    assert Resources("fsgs").read("res/anything") == b"data"
    assert stream.closed
