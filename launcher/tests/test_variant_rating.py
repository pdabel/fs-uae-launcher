import queue
import sqlite3
import threading
from unittest.mock import Mock

import pytest

from fsgs.ogd.client import OGDClient
from launcher.ui import ConfigurationsPanel as panel
from launcher.ui.VariantsBrowser import VariantsBrowser


@pytest.fixture
def rating_worker(monkeypatch):
    callbacks = queue.Queue()
    monkeypatch.setattr(
        panel, "call_after", lambda func, *args: callbacks.put((func, args))
    )
    worker = panel.VariantRatingQueue()

    def drain():
        worker._queue.join()
        while not callbacks.empty():
            func, args = callbacks.get_nowait()
            func(*args)

    return worker, drain


def test_ordered_worker_updates_cache_and_selected_variant(
    monkeypatch, rating_worker
):
    worker, drain = rating_worker
    main_thread = threading.get_ident()
    entered, release = threading.Event(), threading.Event()
    calls = []
    records = []
    selected = ["a"]
    settings = []
    items = [
        {"uuid": "a", "personal_rating": 0},
        {"uuid": "b", "personal_rating": 0},
    ]
    browser = Mock(items=items)

    def rate(_client, variant_uuid, like):
        calls.append((threading.get_ident(), variant_uuid, like))
        if len(calls) == 1:
            entered.set()
            assert release.wait(5)
        return {"like": like, "work": 4}

    class Database:
        def __init__(self):
            records.append(("open", threading.get_ident()))
            self.connection = sqlite3.connect(":memory:")
            self.connection.execute(
                "CREATE TABLE rating (game_uuid TEXT PRIMARY KEY, "
                "work_rating INT, like_rating INT)"
            )

        def cursor(self):
            records.append(("cursor", threading.get_ident()))
            return self.connection.cursor()

        def commit(self):
            records.append(("commit", threading.get_ident()))
            self.connection.commit()
            records.append(
                (
                    "rows",
                    self.connection.execute(
                        "SELECT game_uuid, like_rating FROM rating ORDER BY game_uuid"
                    ).fetchall(),
                )
            )

    database = []

    def instance():
        if not database:
            database.append(Database())
        return database[0]

    def broadcast(signal, variant_uuid, rating):
        assert threading.get_ident() == main_thread
        assert signal == "variant_rating"
        VariantsBrowser.on_variant_rating_signal(browser, variant_uuid, rating)

    monkeypatch.setattr(panel.OGDClient, "rate_variant", rate)
    monkeypatch.setattr(panel.Database, "instance", instance)
    monkeypatch.setattr(panel.LauncherSignal, "broadcast", broadcast)
    monkeypatch.setattr(panel.LauncherConfig, "get", lambda *args: selected[0])
    monkeypatch.setattr(
        panel.LauncherSettings,
        "set",
        lambda key, value: settings.append(
            (threading.get_ident(), key, value)
        ),
    )
    worker.submit("a", 5)
    assert entered.wait(5)
    worker.submit("a", 1)
    worker.submit("b", 4)
    selected[0] = "b"
    release.set()
    drain()

    assert [(uuid, rating) for _, uuid, rating in calls] == [
        ("a", 5),
        ("a", 1),
        ("b", 4),
    ]
    assert all(thread != main_thread for thread, _, _ in calls)
    assert all(
        thread != main_thread for kind, thread in records if kind != "rows"
    )
    assert records[-1] == ("rows", [("a", 1), ("b", 4)])
    assert [item["personal_rating"] for item in items] == [1, 4]
    assert settings == [(main_thread, "__variant_rating", "4")]


@pytest.mark.parametrize("failure", ["network", "database"])
def test_failure_reports_and_does_not_apply(
    monkeypatch, rating_worker, failure
):
    worker, drain = rating_worker
    database = Mock()
    database.connection = object()
    if failure == "network":
        monkeypatch.setattr(
            panel.OGDClient,
            "rate_variant",
            Mock(side_effect=RuntimeError("network")),
        )
    else:
        monkeypatch.setattr(
            panel.OGDClient,
            "rate_variant",
            Mock(return_value={"like": 5, "work": 4}),
        )
        database.cursor.return_value.execute.side_effect = [
            None,
            RuntimeError("insert"),
        ]
    instance = Mock(return_value=database)
    monkeypatch.setattr(panel.Database, "instance", instance)
    applied = Mock()
    error = Mock()
    monkeypatch.setattr(worker, "_applied", applied)
    monkeypatch.setattr(panel.fsui, "show_error", error)
    worker.submit("a", 5)
    drain()
    applied.assert_not_called()
    error.assert_called_once()
    if failure == "database":
        database.rollback.assert_called_once()
        database.commit.assert_not_called()
    else:
        instance.assert_not_called()


def test_choice_restores_confirmed_rating_while_request_is_pending(
    monkeypatch,
):
    choice = Mock()
    choice.get_index.return_value = 1
    choice.index_to_rating = panel.RatingChoice.index_to_rating
    monkeypatch.setattr(panel.LauncherConfig, "get", lambda *args: "a")
    monkeypatch.setattr(panel.LauncherSettings, "get", lambda *args: "1")
    panel.RatingChoice.on_changed(choice)
    choice.on___variant_rating_setting.assert_called_once_with("1")
    choice.set_rating_for_variant.assert_called_once_with("a", 5)


def test_failed_newer_request_retains_earlier_success(
    monkeypatch, rating_worker
):
    worker, drain = rating_worker
    rate = Mock(side_effect=[{"like": 5, "work": 4}, RuntimeError("offline")])
    monkeypatch.setattr(panel.OGDClient, "rate_variant", rate)
    monkeypatch.setattr(panel.Database, "instance", Mock(return_value=Mock()))
    monkeypatch.setattr(panel.LauncherConfig, "get", lambda *args: "a")
    settings = Mock()
    errors = Mock()
    monkeypatch.setattr(panel.LauncherSettings, "set", settings)
    monkeypatch.setattr(panel.LauncherSignal, "broadcast", Mock())
    monkeypatch.setattr(panel.fsui, "show_error", errors)
    worker.submit("a", 5)
    worker.submit("a", 1)
    drain()
    settings.assert_called_once_with("__variant_rating", "5")
    errors.assert_called_once()


def test_http_requests_have_timeouts(monkeypatch):
    get, post = Mock(), Mock()
    monkeypatch.setattr("fsgs.ogd.client.requests.get", get)
    monkeypatch.setattr("fsgs.ogd.client.requests.post", post)
    monkeypatch.setattr(
        OGDClient, "auth", staticmethod(lambda: ("token", "value"))
    )
    client = OGDClient()
    client.rate_variant("a", like=5)
    client.post("/test")
    assert get.call_args.kwargs["timeout"] == 30
    assert post.call_args.kwargs["timeout"] == 30
