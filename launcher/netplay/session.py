"""One lobby game, seen from this launcher: hosting it or joined to it.

The lobby holds the config document and every slot's ready state (see
lobby_client.py). NetplaySession keeps this launcher in step with it:

- every launcher applies each new config version and reports the hash
  and missing files it got, so readiness is the server's answer rather
  than something typed in a channel. The host skips a version older
  than its own edits, so the echo of one push can't undo the next;
- the host pushes its config whenever one of the game's sync keys
  changes locally, which clears everyone's ready on the server, and
  can't start until the lobby has the edit;
- a player who edits a key the document sets gets the document back,
  and reports again;
- when the game turns "running", every launcher starts FS-UAE.

Lobby calls run on one worker thread, in order, so a slow lobby never
blocks the UI; everything else — applying config, callbacks — runs on
the UI thread via dispatch. Both are injectable for tests.
"""

from concurrent.futures import ThreadPoolExecutor

from .lobby_client import (
    SLOT_EMPTY,
    SLOT_MISMATCH,
    SLOT_MISSING,
    SLOT_READY,
    STATE_CONFIGURING,
    STATE_CREATED,
    STATE_ENDED,
    STATE_READY,
    STATE_RUNNING,
    SessionWatcher,
)

# The keys the lobby writes into every document itself; a host's document
# must leave them out.
SERVER_OWNED_KEYS = frozenset(
    [
        "__netplay_game",
        "__netplay_password",
        "__netplay_players",
        "__netplay_port",
        "__netplay_addresses",
    ]
)

PRE_START = (STATE_CREATED, STATE_CONFIGURING, STATE_READY)

# How long the host waits after a local change before pushing, so a burst
# of changes — loading a game sets dozens of keys — is one config version.
PUSH_DELAY_MS = 300


def describe_missing(missing):
    """x_floppy_drive_0_sha1 -> floppy_drive_0, for messages."""
    return ", ".join(
        key.removeprefix("x_").removesuffix("_sha1") for key in sorted(missing)
    )


class NetplaySession:
    def __init__(
        self,
        client,
        game_id,
        slot,
        player_token,
        host_token=None,
        sync_keys=(),
        *,
        apply,
        local_value,
        launch,
        dispatch,
        later,
        on_change=lambda session: None,
        on_message=lambda text, warning=False: None,
        executor=None,
        watcher_factory=SessionWatcher,
    ):
        """
        apply(snapshot) -> (hash, missing) applies a document locally;
        local_value(key) reads this launcher's config; launch(snapshot)
        starts FS-UAE; dispatch(fn, *args) runs fn on the UI thread;
        later(ms, fn) runs it there after a delay. sync_keys is what the
        host created the game with: the keys its document carries.
        """
        self.client = client
        self.game_id = game_id
        self.slot = slot
        self.player_token = player_token
        self.host_token = host_token
        self.sync_keys = [k for k in sync_keys if k not in SERVER_OWNED_KEYS]
        self._apply = apply
        self._local_value = local_value
        self._launch = launch
        self._dispatch = dispatch
        self._later = later
        self._on_change = on_change
        self._on_message = on_message
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="lobby"
        )
        self._watcher = watcher_factory(
            client, game_id, self._watched, self._watch_failed
        )

        self.snapshot = None
        self.ended = False
        self.launched = False
        self.applied_version = 0
        self._lost = False
        self._last_pushed = None
        self._pushed_version = 0
        self._pushing = False
        self._push_again = False
        self._push_scheduled = False
        self._applying = False
        self._restore_scheduled = False

    @property
    def is_host(self):
        return self.host_token is not None

    @property
    def state(self):
        return self.snapshot["state"] if self.snapshot else STATE_CREATED

    def start(self):
        self._watcher.start()
        if self.is_host:
            self._push_if_changed()

    # --- From the watcher thread -----------------------------------------

    def _watched(self, snapshot):
        self._dispatch(self._handle, snapshot)

    def _watch_failed(self, error):
        self._dispatch(self._lobby_unreachable, error)

    # --- On the UI thread --------------------------------------------------

    def _lobby_unreachable(self, error):
        if not self.ended and not self._lost:
            self._lost = True
            self._message(f"lost the lobby, retrying: {error}", True)

    def _handle(self, snapshot):
        if self.ended:
            return
        if self._lost:
            self._lost = False
            self._message("lobby reachable again")
        state = snapshot["state"]
        if state == STATE_ENDED:
            if self.snapshot is not None:
                self.snapshot = dict(self.snapshot, state=STATE_ENDED)
            else:
                self.snapshot = snapshot
            self._finish()
            self._message("the game has ended")
            self._on_change(self)
            return
        self.snapshot = snapshot
        if (
            state in PRE_START
            and snapshot["config"] is not None
            and snapshot["config_version"] != self.applied_version
        ):
            if self.is_host and not self._is_local_document(snapshot):
                # The host has edits newer than this version; applying it
                # would undo them. Their own version follows the push.
                self._push_if_changed()
            else:
                self._apply_and_report(snapshot)
        self._on_change(self)
        if state == STATE_RUNNING and not self.launched:
            self.launched = True
            if self._restore_scheduled:
                # A player's edit hadn't been put back yet: launch the
                # game's config, not the edit.
                self._restore_scheduled = False
                self._apply_quietly(snapshot)
            self._launch(snapshot)

    def _apply_quietly(self, snapshot):
        """Apply snapshot without reacting to the changes it makes."""
        self._applying = True
        try:
            return self._apply(snapshot)
        finally:
            self._applying = False

    def _apply_and_report(self, snapshot):
        version = snapshot["config_version"]
        config_hash, missing = self._apply_quietly(snapshot)
        self.applied_version = version
        if missing:
            self._message(
                f"could not find {describe_missing(missing)}; add the "
                f"files and press Re-check",
                True,
            )
        self._call(
            self.client.report_ready,
            self.game_id,
            self.slot,
            self.player_token,
            version,
            config_hash,
            missing,
            what="report ready",
        )

    def recheck(self):
        """Apply the current document again, after adding missing files."""
        if self.snapshot and self.state in PRE_START:
            self.applied_version = 0
            self._handle(self.snapshot)

    def config_changed(self, key):
        """A local config key changed: the host pushes, after a pause; a
        player gets the game's config back."""
        if self.ended or self._applying:
            return
        if not self.is_host:
            self._player_changed(key)
            return
        if key not in self.sync_keys or self._push_scheduled:
            return
        self._push_scheduled = True
        self._on_change(self)  # can_start is now false

        def push():
            self._push_scheduled = False
            self._push_if_changed()

        self._later(PUSH_DELAY_MS, push)

    def _player_changed(self, key):
        """A player edited a key the game's config sets.

        Their ready on the server is for the game's value, so the edit
        can't stand: the document is applied again, after a pause so a
        burst of changes is one restore, and readiness reported anew.
        """
        config = self.snapshot["config"] if self.snapshot else None
        if (
            self._restore_scheduled
            or self.state not in PRE_START
            or config is None
            or key not in config
            or str(self._local_value(key)) == config[key]
        ):
            return
        self._restore_scheduled = True

        def restore():
            if not self._restore_scheduled:
                return  # done at launch instead
            self._restore_scheduled = False
            if self.ended or self.state not in PRE_START:
                return
            self._message(
                "the game's config is set by the host; restoring it", True
            )
            self.recheck()

        self._later(PUSH_DELAY_MS, restore)

    def _local_document(self):
        return {key: str(self._local_value(key)) for key in self.sync_keys}

    def _is_local_document(self, snapshot):
        """Host: whether snapshot's config is this launcher's current one."""
        config = snapshot["config"]
        return all(
            config.get(key) == value
            for key, value in self._local_document().items()
        )

    @property
    def sending_config(self):
        """Host: local edits the lobby hasn't confirmed yet."""
        if not self.is_host:
            return False
        if (
            self._push_scheduled
            or self._pushing
            or self._local_document() != self._last_pushed
        ):
            return True
        # Pushed, but the snapshot on screen is from before the push.
        return bool(self.snapshot) and (
            self.snapshot["config_version"] < self._pushed_version
        )

    @property
    def can_start(self):
        """Host: whether start would be for the config on screen."""
        return (
            self.is_host
            and not self.ended
            and self.state == STATE_READY
            and not self.sending_config
        )

    def _push_if_changed(self):
        if self.ended or self.state not in PRE_START:
            return
        document = self._local_document()
        if document == self._last_pushed:
            # Includes the host applying its own document back: its values
            # are what it sent, so nothing goes out and nothing loops.
            return
        if self._pushing:
            self._push_again = True
            return
        self._pushing = True
        self._last_pushed = document

        def pushed(result, error):
            self._pushing = False
            if error is not None:
                self._last_pushed = None
            elif result:
                self._pushed_version = result.get("config_version", 0)
            if self._push_again:
                self._push_again = False
                self._push_if_changed()
            if not self.ended:
                self._on_change(self)

        self._call(
            self.client.set_config,
            self.game_id,
            self.host_token,
            document,
            what="send config",
            then=pushed,
        )

    def start_game(self):
        """Host: ask the lobby to start; every launcher then sees running."""
        if not self.is_host:
            self._message("only the host can start the game", True)
            return
        if self.sending_config:
            # Starting now would start the version before the edit, while
            # this launcher runs the edit.
            self._message(
                "cannot start yet: your config changes are still being sent",
                True,
            )
            return
        if self.state != STATE_READY:
            self._message(
                "cannot start yet: " + "; ".join(self.waiting_on()), True
            )
            return
        self._call(
            self.client.start, self.game_id, self.host_token, what="start"
        )

    def leave(self):
        """Stop following the game. Before it starts, the host ends it for
        everyone and a player hands their slot back. Once it runs it
        belongs to the players' FS-UAE: the host moving to another
        channel or game must not stop it, and the lobby ends it when a
        player quits."""
        if self.ended:
            return
        if self.is_host and self.state in PRE_START:
            self._call(
                self.client.end, self.game_id, self.host_token, what="end"
            )
        elif self.state in PRE_START:
            self._call(
                self.client.leave,
                self.game_id,
                self.slot,
                self.player_token,
                what="leave",
            )
        self._finish()
        self._on_change(self)

    def _finish(self):
        self.ended = True
        self._watcher.stop()
        self._executor.shutdown(wait=False)

    # --- Views for the panel -----------------------------------------------

    def slot_lines(self):
        """One line per slot for the panel."""
        if not self.snapshot or "slots" not in self.snapshot:
            return []
        lines = []
        for s in self.snapshot["slots"]:
            if s["status"] == SLOT_EMPTY:
                lines.append(f"{s['slot'] + 1}. open")
                continue
            who = s.get("tag") or "?"
            if s["slot"] == self.slot:
                who += " (you)"
            status = s["status"]
            if status == SLOT_MISSING:
                status += ": " + describe_missing(s.get("missing", {}))
            elif status == SLOT_MISMATCH:
                status = "config differs"
            lines.append(f"{s['slot'] + 1}. {who} — {status}")
        return lines

    def waiting_on(self):
        """Why the game can't start, one reason per slot not ready."""
        if not self.snapshot or "slots" not in self.snapshot:
            return ["the lobby has not answered yet"]
        reasons = []
        if self.sending_config:
            reasons.append("your config changes are still being sent")
        for s in self.snapshot["slots"]:
            if s["status"] != SLOT_READY:
                who = s.get("tag") or f"slot {s['slot'] + 1}"
                reasons.append(f"{who} is {s['status']}")
        return reasons or ["the lobby has not reported ready yet"]

    # --- Helpers -------------------------------------------------------

    def _message(self, text, warning=False):
        self._on_message(text, warning)

    def _call(self, fn, *args, what, then=None):
        """Run a lobby call on the worker; report a failure on the UI."""

        def run():
            try:
                result, error = fn(*args), None
            except Exception as e:
                result, error = None, e
            self._dispatch(done, result, error)

        def done(result, error):
            if error is not None and not self.ended:
                self._message(f"could not {what}: {error}", True)
            if then is not None:
                then(result, error)

        try:
            self._executor.submit(run)
        except RuntimeError:
            pass  # shut down: the session has ended
