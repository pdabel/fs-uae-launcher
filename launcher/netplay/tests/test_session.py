"""NetplaySession with a fake lobby, worker and UI thread."""

import pytest

from launcher.netplay.config_apply import resolve_config
from launcher.netplay.lobby_client import LobbyError
from launcher.netplay.session import NetplaySession, describe_missing

SYNC = ["amiga_model", "chip_memory", "__netplay_password", "__netplay_port"]


class FakeClient:
    def __init__(self):
        self.calls = []
        self.fail = {}
        self.results = {}

    def __getattr__(self, name):
        def call(*args):
            self.calls.append((name,) + args)
            if name in self.fail:
                raise self.fail[name]
            return self.results.get(name, {})

        return call

    def named(self, name):
        return [c for c in self.calls if c[0] == name]


class QueuedExecutor:
    """Runs submitted calls only when the test says so."""

    def __init__(self):
        self.queue = []
        self.shut_down = False

    def submit(self, fn):
        if self.shut_down:
            raise RuntimeError("shut down")
        self.queue.append(fn)

    def run_all(self):
        while self.queue:
            self.queue.pop(0)()

    def shutdown(self, wait):
        self.shut_down = True


class FakeWatcher:
    def __init__(self, client, game_id, on_snapshot, on_error):
        self.on_snapshot = on_snapshot
        self.on_error = on_error
        self.started = self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class Harness:
    def __init__(self, host=False, missing=None):
        self.client = FakeClient()
        self.executor = QueuedExecutor()
        self.local = {"amiga_model": "A500", "chip_memory": "512"}
        self.applied = []
        self.launched = []
        self.changes = 0
        self.messages = []
        self.later = []
        self.missing = missing or {}
        self.watchers = []

        def watcher_factory(*args):
            w = FakeWatcher(*args)
            self.watchers.append(w)
            return w

        self.session = NetplaySession(
            self.client,
            "g1",
            0 if host else 1,
            "player-token",
            "host-token" if host else None,
            SYNC,
            apply=self.apply,
            local_value=lambda key: self.local.get(key, ""),
            launch=self.launched.append,
            dispatch=lambda fn, *args: fn(*args),
            later=lambda ms, fn: self.later.append(fn),
            on_change=self.changed,
            on_message=lambda text, warning=False: self.messages.append(
                (text, warning)
            ),
            executor=self.executor,
            watcher_factory=watcher_factory,
        )

    @property
    def watcher(self):
        return self.watchers[0]

    def apply(self, snapshot):
        # Like apply_document: the document's values become the local
        # config, and each change reaches the session as the launcher's
        # config listener would pass it on.
        self.applied.append(snapshot["config_version"])
        for key, value in snapshot["config"].items():
            if self.local.get(key) != value:
                self.local[key] = value
                self.session.config_changed(key)
        return f"hash-{snapshot['config_version']}", dict(self.missing)

    def changed(self, session):
        self.changes += 1

    def see(self, state, version=1, slots=None, config=True):
        if config is True:
            config = {"amiga_model": "A500"}
        self.watcher.on_snapshot(
            {
                "state": state,
                "config_version": version,
                "config": config or None,
                "slots": slots or [],
            }
        )
        self.executor.run_all()

    def edit(self, key, value):
        self.local[key] = value
        self.session.config_changed(key)

    def warnings(self):
        return [text for text, warning in self.messages if warning]


def test_player_applies_each_version_once_and_reports():
    h = Harness()
    h.session.start()
    assert h.watcher.started
    h.see("created", version=0, config=False)
    assert h.applied == []

    h.see("configuring", version=1)
    h.see("configuring", version=1)
    assert h.applied == [1]
    assert h.client.named("report_ready") == [
        ("report_ready", "g1", 1, "player-token", 1, "hash-1", {})
    ]
    h.see("configuring", version=2)
    assert h.applied == [1, 2]
    assert h.changes == 4


def test_missing_files_are_reported_and_named():
    h = Harness(missing={"x_floppy_drive_0_sha1": "f" * 40})
    h.session.start()
    h.see("configuring")
    assert h.client.named("report_ready")[0][-1] == {
        "x_floppy_drive_0_sha1": "f" * 40
    }
    assert any("floppy_drive_0" in w for w in h.warnings())


def test_recheck_applies_the_same_version_again():
    h = Harness()
    h.session.start()
    h.see("configuring")
    h.session.recheck()
    h.executor.run_all()
    assert h.applied == [1, 1]
    assert len(h.client.named("report_ready")) == 2


def test_host_pushes_its_document_without_server_keys():
    h = Harness(host=True)
    h.session.start()
    h.executor.run_all()
    assert h.client.named("set_config") == [
        (
            "set_config",
            "g1",
            "host-token",
            {"amiga_model": "A500", "chip_memory": "512"},
        )
    ]


def test_host_pushes_once_per_burst_and_only_on_change():
    h = Harness(host=True)
    h.session.start()
    h.executor.run_all()

    # The host applying its own document back changes nothing to push.
    h.see("configuring")
    assert len(h.client.named("set_config")) == 1

    h.local["chip_memory"] = "1024"
    h.session.config_changed("chip_memory")
    h.session.config_changed("amiga_model")
    h.session.config_changed("kickstart_file")  # not a sync key
    assert len(h.later) == 1
    h.later.pop()()
    h.executor.run_all()
    pushes = h.client.named("set_config")
    assert len(pushes) == 2
    assert pushes[-1][-1]["chip_memory"] == "1024"


def test_a_change_during_a_push_is_pushed_after_it():
    h = Harness(host=True)
    h.session.start()  # first push queued, not yet run
    h.local["amiga_model"] = "A1200"
    h.session.config_changed("amiga_model")
    h.later.pop()()  # second push waits for the first
    assert len(h.executor.queue) == 1
    h.executor.run_all()
    pushes = h.client.named("set_config")
    assert [p[-1]["amiga_model"] for p in pushes] == ["A500", "A1200"]


def test_failed_push_is_retried_on_the_next_change():
    h = Harness(host=True)
    h.client.fail["set_config"] = LobbyError(400, "bad key")
    h.session.start()
    h.executor.run_all()
    assert any("could not send config: bad key" in w for w in h.warnings())

    del h.client.fail["set_config"]
    h.session.config_changed("amiga_model")
    h.later.pop()()
    h.executor.run_all()
    # Same document as the failed push, but it never arrived: sent again.
    assert len(h.client.named("set_config")) == 2


@pytest.mark.parametrize("with_snapshot", [False, True])
def test_recheck_retries_failed_initial_publication(with_snapshot):
    h = Harness(host=True)
    published = []
    h.session._on_initial_config = lambda: published.append(True)
    h.session._initial_config_pending = True
    h.client.results["set_config"] = {"config_version": 1}
    h.client.fail["set_config"] = ConnectionError("offline")
    h.session.start()
    h.executor.run_all()
    if with_snapshot:
        h.see("created", version=0, config=False)
    assert published == []
    assert any("could not send config" in warning for warning in h.warnings())

    del h.client.fail["set_config"]
    h.session.recheck()
    h.executor.run_all()
    assert len(h.client.named("set_config")) == 2
    assert published == [True]


def test_running_launches_once():
    h = Harness()
    h.session.start()
    h.see("ready")
    h.see("running")
    h.see("running")
    assert len(h.launched) == 1
    assert h.launched[0]["state"] == "running"


def test_start_game():
    h = Harness(host=True)
    h.session.start()
    h.see(
        "configuring",
        slots=[
            {"slot": 0, "status": "ready", "tag": "HST"},
            {"slot": 1, "status": "missing", "tag": "PL2"},
        ],
    )
    h.session.start_game()
    assert h.client.named("start") == []
    assert any("PL2 is missing" in w for w in h.warnings())

    h.see("ready")
    h.session.start_game()
    h.executor.run_all()
    assert h.client.named("start") == [("start", "g1", "host-token")]


def test_only_the_host_starts():
    h = Harness()
    h.session.start()
    h.see("ready")
    h.session.start_game()
    assert h.client.named("start") == []
    assert h.warnings() == ["only the host can start the game"]


def test_ended_stops_everything():
    h = Harness()
    h.session.start()
    h.see("configuring")
    h.watcher.on_snapshot({"id": "g1", "state": "ended"})
    assert h.session.ended and h.watcher.stopped and h.executor.shut_down
    assert h.session.state == "ended"
    changes = h.changes
    h.watcher.on_snapshot({"state": "running", "config_version": 1})
    assert h.changes == changes and h.launched == []


@pytest.mark.parametrize(
    "host, call",
    [
        (True, ("end", "g1", "host-token")),
        (False, ("leave", "g1", 1, "player-token")),
    ],
)
def test_leave(host, call):
    h = Harness(host=host)
    h.session.start()
    h.executor.run_all()
    h.session.leave()
    h.executor.run_all()
    assert h.client.calls[-1] == call
    assert h.session.ended


@pytest.mark.parametrize("host", [True, False])
def test_leaving_a_running_game_keeps_it_running(host):
    # The host joining another channel or starting another game must
    # not end the one its players are in.
    h = Harness(host=host)
    h.session.start()
    h.see("running")
    calls = len(h.client.calls)
    h.session.leave()
    h.executor.run_all()
    assert h.client.calls[calls:] == []
    assert h.session.ended and h.watcher.stopped


def test_lost_lobby_is_reported_once():
    h = Harness()
    h.session.start()
    h.watcher.on_error(ConnectionError("refused"))
    h.watcher.on_error(ConnectionError("refused"))
    assert len(h.warnings()) == 1
    h.see("configuring")
    assert h.messages[-1] == ("lobby reachable again", False)


def test_slot_lines():
    h = Harness()
    h.session.start()
    h.see(
        "configuring",
        slots=[
            {"slot": 0, "status": "ready", "tag": "HST"},
            {
                "slot": 1,
                "status": "missing",
                "tag": "PL2",
                "missing": {"x_cdrom_drive_0_sha1": "c" * 40},
            },
            {"slot": 2, "status": "mismatch", "tag": "PL3"},
            {"slot": 3, "status": "empty"},
        ],
    )
    assert h.session.slot_lines() == [
        "1. HST — ready",
        "2. PL2 (you) — missing: cdrom_drive_0",
        "3. PL3 — config differs",
        "4. open",
    ]


def test_describe_missing():
    assert (
        describe_missing(
            {"x_floppy_drive_1_sha1": "a", "x_kickstart_file_sha1": "b"}
        )
        == "floppy_drive_1, kickstart_file"
    )


HOST_DOC = {"amiga_model": "A500", "chip_memory": "512"}


def test_an_echo_of_an_older_version_does_not_undo_a_host_edit():
    h = Harness(host=True)
    h.session.start()
    h.executor.run_all()  # A500 sent
    h.edit("amiga_model", "A1200")  # push scheduled, not yet sent

    # The lobby's answer to the A500 push arrives first.
    h.see("configuring", version=1, config=dict(HOST_DOC))
    assert h.applied == []
    assert h.local["amiga_model"] == "A1200"

    h.later.pop()()
    h.executor.run_all()
    pushes = h.client.named("set_config")
    assert [p[-1]["amiga_model"] for p in pushes] == ["A500", "A1200"]


def test_the_host_applies_and_reports_its_own_current_document():
    h = Harness(host=True)
    h.session.start()
    h.executor.run_all()
    h.see("configuring", version=1, config=dict(HOST_DOC))
    assert h.applied == [1]
    assert len(h.client.named("report_ready")) == 1


def test_host_hash_mismatch_identifies_keys_without_values():
    h = Harness(host=True)
    h.local["amiga_model"] = "A1200"
    h.session._apply = lambda snapshot: ("local-hash", {})
    h.session._apply_and_report(
        {
            "config_version": 1,
            "config": {"amiga_model": "A1200", "chip_memory": "512"},
            "hash": "lobby-hash",
            "keys": {"checksum": ["amiga_model", "chip_memory"]},
        }
    )

    assert h.warnings() == [
        "host config differs from the lobby for: checksum calculation"
    ]


def test_host_republishes_config_changed_while_applying():
    h = Harness(host=True)
    key = "x_kickstart_file_sha1"
    h.session.sync_keys.append(key)
    h.local[key] = "old-sha"

    def apply(snapshot):
        h.local[key] = "new-sha"
        return "local-hash", {}

    h.session._apply = apply
    h.session.start()
    h.executor.run_all()
    h.session._handle(
        {
            "state": "configuring",
            "config_version": 1,
            "config": {**HOST_DOC, key: "old-sha"},
            "hash": "lobby-hash",
            "keys": {"checksum": ["amiga_model", "chip_memory", key]},
            "slots": [],
        }
    )
    h.executor.run_all()

    pushes = h.client.named("set_config")
    assert len(pushes) == 2
    assert pushes[1][-1][key] == "new-sha"
    assert h.client.named("report_ready") == []


@pytest.mark.parametrize("changed", [False, True])
def test_host_preserves_missing_media_when_applying_config(changed):
    h = Harness(host=True)
    missing_key = "x_floppy_drive_0_sha1"
    requested = "d" * 40
    h.session.sync_keys.append(missing_key)
    h.local[missing_key] = requested
    document = {**HOST_DOC, missing_key: requested}

    def apply(snapshot):
        updates, missing = resolve_config(
            snapshot["config"], set(h.session.sync_keys), lambda sha1: None
        )
        h.local.update(updates)
        if changed:
            h.local["chip_memory"] = "1024"
        return "local-hash", missing

    h.session._apply = apply
    h.session.start()
    h.executor.run_all()
    h.session._handle({
        "state": "configuring",
        "config_version": 1,
        "config": document,
        "hash": "lobby-hash",
        "keys": {"checksum": list(document)},
        "slots": [],
    })
    h.executor.run_all()

    pushes = h.client.named("set_config")
    assert len(pushes) == (2 if changed else 1)
    assert pushes[-1][-1][missing_key] == requested
    assert pushes[-1][-1]["chip_memory"] == ("1024" if changed else "512")
    assert any("floppy_drive_0" in warning for warning in h.warnings())
    if not changed:
        assert h.client.named("report_ready")[0][-1] == {missing_key: requested}
        assert not h.session.sending_config
    else:
        published = dict(pushes[-1][-1])
        h.session._handle({
            "state": "configuring",
            "config_version": 2,
            "config": published,
            "hash": "new-hash",
            "keys": {"checksum": list(published)},
            "slots": [],
        })
        h.executor.run_all()
        assert len(h.client.named("set_config")) == 2
        assert h.client.named("report_ready")[-1][-1] == {missing_key: requested}
        assert not h.session.sending_config

    h.local[missing_key] = "e" * 40
    h.session.config_changed(missing_key)
    h.later.pop()()
    h.executor.run_all()
    assert h.client.named("set_config")[-1][-1][missing_key] == "e" * 40


def test_host_can_explicitly_clear_an_unresolved_media_slot():
    h = Harness(host=True)
    key = "x_floppy_drive_0_sha1"
    requested = "d" * 40
    h.session.sync_keys.append(key)
    h.local[key] = requested

    def apply(snapshot):
        h.local[key] = ""
        return "local-hash", {key: requested}

    h.session._apply = apply
    h.session.start()
    h.executor.run_all()
    h.session._handle({
        "state": "configuring",
        "config_version": 1,
        "config": {**HOST_DOC, key: requested},
        "slots": [],
    })
    h.executor.run_all()

    h.session.config_changed(key)
    h.later.pop()()
    h.executor.run_all()
    assert h.client.named("set_config")[-1][-1][key] == ""


def test_start_waits_for_an_edit_to_reach_the_lobby():
    h = Harness(host=True)
    h.session.start()
    h.executor.run_all()
    h.see("ready", version=1, config=dict(HOST_DOC))
    assert h.session.can_start

    h.edit("chip_memory", "1024")
    assert not h.session.can_start
    h.session.start_game()
    assert h.client.named("start") == []
    assert any("still being sent" in w for w in h.warnings())

    # Sent, but the snapshot on screen is still the version before it.
    h.client.results["set_config"] = {"config_version": 2}
    h.later.pop()()
    h.executor.run_all()
    assert not h.session.can_start
    h.session.start_game()
    assert h.client.named("start") == []

    h.see("ready", version=2, config=dict(HOST_DOC, chip_memory="1024"))
    assert h.session.can_start
    h.session.start_game()
    h.executor.run_all()
    assert h.client.named("start") == [("start", "g1", "host-token")]


def test_a_players_edit_is_restored_and_reported_again():
    h = Harness()
    h.session.start()
    h.see("ready")
    assert h.applied == [1]

    h.edit("kickstart_file", "my.rom")  # not in the document
    assert h.later == []
    h.edit("amiga_model", "A1200")
    h.edit("amiga_model", "A4000")
    assert len(h.later) == 1
    h.later.pop()()
    h.executor.run_all()

    assert h.local["amiga_model"] == "A500"
    assert h.applied == [1, 1]
    assert len(h.client.named("report_ready")) == 2
    assert any("set by the host" in w for w in h.warnings())


def test_applying_the_document_is_not_a_players_edit():
    h = Harness()
    h.local["amiga_model"] = "A1200"
    h.session.start()
    h.see("configuring")  # apply changes amiga_model to A500
    assert h.later == []


def test_a_players_unrestored_edit_is_undone_before_launch():
    h = Harness()
    h.session.start()
    h.see("ready")
    h.edit("amiga_model", "A1200")

    launched_with = []
    h.session._launch = lambda snapshot: launched_with.append(
        h.local["amiga_model"]
    )
    h.see("running")
    assert launched_with == ["A500"]
    # The restore that was pending has nothing left to do.
    h.later.pop()()
    h.executor.run_all()
    assert not any("set by the host" in w for w in h.warnings())


@pytest.mark.parametrize(
    "auto_start, slots, state, want",
    [
        (
            True,
            [("HST", "ready"), (None, "empty")],
            "configuring",
            "Starts when 1 more player joins and is ready.",
        ),
        (
            False,
            [("HST", "ready"), (None, "empty"), (None, "empty")],
            "configuring",
            "Can start when 2 more players join and are ready.",
        ),
        (
            True,
            [("HST", "ready"), ("PL2", "missing"), ("PL3", "waiting")],
            "configuring",
            "Starts when you're ready: add the missing file, then Re-check.",
        ),
        (
            False,
            [("HST", "ready"), ("PL2", "missing")],
            "configuring",
            "Add the missing file, then Re-check.",
        ),
        (
            True,
            [("HST", "mismatch"), ("PL2", "ready"), (None, "empty")],
            "configuring",
            "Waiting: HST's config differs; 1 more player to join.",
        ),
        (
            True,
            [("HST", "waiting"), ("PL2", "ready")],
            "configuring",
            "Waiting: HST is checking the config.",
        ),
        (True, [("HST", "ready"), ("PL2", "ready")], "ready", "Starting…"),
        (
            False,
            [("HST", "ready"), ("PL2", "ready")],
            "ready",
            "Everyone is ready: waiting for the host to start.",
        ),
        (False, [("HST", "ready"), ("PL2", "ready")], "running", "Starting…"),
    ],
)
def test_status_line(auto_start, slots, state, want):
    h = Harness()
    h.session.snapshot = {
        "state": state,
        "auto_start": auto_start,
        "config_version": 1,
        "slots": [
            {"slot": i, "status": status, "tag": tag}
            for i, (tag, status) in enumerate(slots)
        ],
    }
    assert h.session.status_line() == want


def test_status_line_before_the_lobby_answers():
    assert Harness().session.status_line() == "Waiting for the lobby…"
