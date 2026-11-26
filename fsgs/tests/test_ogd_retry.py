import pytest

from fsgs.ogd.base import SynchronizerBase


@pytest.mark.parametrize("kind", ["json", "data"])
def test_retry_status_and_cancellation(monkeypatch, kind):
    statuses = []
    sleeps = []
    synchronizer = SynchronizerBase(
        None, on_status=statuses.append, stop_check=lambda: True
    )

    def fail(url):
        raise Exception("boom")

    monkeypatch.setattr(synchronizer, f"fetch_{kind}_attempt", fail)
    monkeypatch.setattr("fsgs.ogd.base.time.sleep", sleeps.append)
    monkeypatch.setattr("fsgs.ogd.base.gettext", lambda message: message)

    assert getattr(synchronizer, f"fetch_{kind}")("url") is None
    assert statuses == [
        ("Download failed (attempt 1) - retrying in 2 seconds", "")
    ]
    assert sleeps == [0.1]


@pytest.mark.parametrize("kind", ["json", "data"])
def test_retry_delay_tracks_later_attempts(monkeypatch, kind):
    statuses = []
    sleeps = []
    attempts = []
    synchronizer = SynchronizerBase(None, on_status=statuses.append)

    def fetch(url):
        attempts.append(url)
        if len(attempts) <= 5:
            raise Exception("boom")
        return "success"

    monkeypatch.setattr(synchronizer, f"fetch_{kind}_attempt", fetch)
    monkeypatch.setattr("fsgs.ogd.base.time.sleep", sleeps.append)
    monkeypatch.setattr("fsgs.ogd.base.gettext", lambda message: message)

    assert getattr(synchronizer, f"fetch_{kind}")("url") == "success"
    assert len(attempts) == 6
    assert statuses[-2:] == [
        ("Download failed (attempt 5) - retrying in 3 seconds", ""),
        ("Retrying last operation (attempt 5)", ""),
    ]
    assert sleeps == [0.1] * (20 * 4 + 30)
