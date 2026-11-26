# FIXME Implementation Plan

This plan covers the 25 `FIXME` markers still in the code after the
Priority 5 triage (see [todo-fixme-inventory.md](todo-fixme-inventory.md)).
Every other marker was checked and either removed or replaced with a plain
note, because it was stale, already handled, speculative, or in dead code.

Each task below is self-contained so it can be handed to a smaller model.
Each one is a **separate branch** with **one commit**.

## Rules for every task

1. **Branch from the triage branch**, not `main`, because the four earlier
   FIXME branches are not merged yet:

   ```sh
   git fetch origin
   git switch -c <branch> --no-track origin/chore/priority-5-fixme-triage
   ```

2. **Only touch the files listed in the task.** If something else seems
   wrong, note it in the PR description instead of fixing it.
3. **Remove the task's FIXME markers** as part of the fix. When done,
   `git grep -n FIXME -- <files in the task>` must not show them.
4. **Add the tests the task lists**, in the file it names. Each test must
   fail without the fix.
5. **Run these checks** before committing. All must pass, except the Qt suite's
   19 existing failures in `test_fusion_and_removed_theme_migration` and
   `test_workspace_settings_navigation`, which also fail on the base branch.
   Use `venv-3.12/bin` if `venv/bin` does not exist.

   ```sh
   venv/bin/black --check . && venv/bin/ruff check
   venv/bin/mypy
   venv/bin/python -m pytest fsbc fstd fspy fsgs/tests fsbuild/tests launcher/netplay launcher/server/tests launcher/tests
   QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest fsui/test
   ```

6. **Update the docs** named in the task, and mark the task complete in the
   status table below.
7. **Commit** with the message given in the task, plus the trailer
   `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`,
   then `git push -u origin <branch>`.
8. **Never** use `pipenv run` (it can rewrite `Pipfile.lock`), add
   dependencies, or do network or disk I/O on the Qt thread.

## Status

| # | Branch | Size | Status |
|---|---|---|---|
| T1 | `fix/update-check-timeout` | XS | Complete |
| T2 | `fix/ogd-retry-countdown` | XS | Complete |
| T3 | `fix/uae-sana2-explicit-value` | XS | Complete |
| T4 | `fix/variant-rating-off-ui-thread` | S | Pending |
| T5 | `fix/arm64-plugin-arch` | S | Pending |
| T6 | `fix/options-behavior-disconnect` | XS | Pending |
| T7 | `refactor/floppy-extensions` | S | Pending |
| T8 | `fix/save-config-empty-name` | XS | Pending |
| T9 | `fix/textarea-monospace-font` | XS | Pending |
| T10 | `fix/combobox-read-only` | S | Pending |
| T11 | `chore/remove-unused-vsync-code` | M | Pending |

Tasks are independent and can land in any order. Suggested order is the
table order: smallest and most valuable first.

---

## T1 - Update check: add a timeout

**Completed:** The request has a 10-second connect/read timeout. The
`update_available` broadcast remains: no in-tree listener was found, but
that does not establish that external listeners do not use the signal.
Request errors continue to be reported by the worker's traceback.

**Why it was worth it:** `requests.get` in the update check had no timeout,
which broke the "every HTTP call has a timeout" rule in `AGENTS.md`. A
hanging server could leave the worker thread stuck forever.

**Files:** `launcher/update_manager.py`, new `launcher/tests/test_update_manager.py`.

**Facts already checked:**
- `run_update_check()` runs `_update_thread_function()` on a
  `threading.Thread`.
- `LauncherSettings.set()` is safe from a worker: `Signal.notify()` in
  `fsbc/signal.py` queues notifications from other threads for the main
  thread. So the "Thread safety" FIXME is already handled.
- No in-tree code listens to `LauncherSignal.broadcast("update_available", ...)`.
  The status bar (`WarningsElement.on___update_available_setting`) uses the
  `__update_available` setting, but external listeners may use the broadcast.

**Steps:**
1. Add `timeout=10` to `requests.get(url)` in `_update_thread_function`.
2. Keep the existing broadcast and download URL for potential external
   listeners.
3. Replace both FIXME lines with one comment:
   `# Safe from this worker thread: setting signals are queued for the UI.`

**Tests** (`launcher/tests/test_update_manager.py`): monkeypatch
`launcher.update_manager.requests.get` with a fake that records its kwargs and
returns an object with `.text = "99.0.0"` and a no-op `raise_for_status()`.
Monkeypatch `LauncherSettings.set` to record calls. Call
`UpdateManager._update_thread_function()` and assert `timeout` was passed and
`("__update_available", "99.0.0")` was set. Also monkeypatch
`UpdateManager.series` to return `"stable"`, because the real one needs a
running `Application`. Cover old and placeholder versions, the broadcast,
and logging of timeouts and HTTP errors as well.

**Commit:** `fix: time out the launcher update check`

---

## T2 - Show the real retry delay in OGD download errors

**Why it's worth it:** user-visible bug. `fsgs/ogd/base.py` shows
"retrying in {0} seconds" with the *attempt number* as the seconds.

**Files:** `fsgs/ogd/base.py`, `fsgs/ogd/GameDatabaseSynchronizer.py`,
new `fsgs/tests/test_ogd_retry.py`.

**Facts already checked:** every `po/*.po` already has the corrected msgid
`"Download failed (attempt {0}) - retrying in {1} seconds"` (used by
`GameDatabaseSynchronizer.py`). Serbian and Swedish entries are untranslated
and fall back to the English msgid. Don't edit any `.po` files.

**Steps:**
1. In both `fetch_json` and `fetch_data` in `base.py`, change the msgid to
   exactly `"Download failed (attempt {0}) - " "retrying in {1} seconds"`
   (same text as `GameDatabaseSynchronizer.py`).
2. Delete the four `# FIXME: change second {0} to {1}` lines (two in each
   file). The two in `GameDatabaseSynchronizer.py` are stale.

**Tests:** create `SynchronizerBase(None, on_status=statuses.append,
stop_check=lambda: True)` and monkeypatch its `fetch_json_attempt` (and, in
a second test, `fetch_data_attempt`) to raise `Exception("boom")`. Patch
`fsgs.ogd.base.time.sleep` to do nothing. `stop_check` returning `True` makes
`fetch_json` return `None` after the first failure. `on_status` receives
`(title, status)` tuples, so assert `statuses[0][0]` contains
`"(attempt 1) - retrying in 2 seconds"`.

**Commit:** `fix: show the retry delay, not the attempt, in download errors`

---

## T3 - `uae_sana2` copies the wrong option

**Why it's worth it:** real bug. In `launcher/ui/config/expand.py`,
`_uae_sana2` sets `value = c.uae_rtc.explicit` when `uae_sana2` is set
explicitly, so a user's `uae_sana2` value is replaced by their `uae_rtc`
value (usually empty).

**Files:** `launcher/ui/config/expand.py`, new
`launcher/tests/test_expand_config.py`.

**Note:** `expand.py` says "Automatically generated", but its generator is
not in this repository. Edit it by hand and keep the header.

**Steps:**
1. In `_uae_sana2`, change `c.uae_rtc.explicit` to `c.uae_sana2.explicit`.
2. Delete its two FIXME lines. Don't change other functions.

**Tests:** build the config the same way `launcher/implicit_handler.py` does:

```python
from launcher.implicit_handler import ExpandFunctions
from launcher.ui.config.expand import expand_config
from launcher.ui.config.model import ImplicitConfig

class Values(dict):
    def get(self, key, default=""):
        return super().get(key, default)

implicit = ImplicitConfig(Values(uae_sana2="true"), Values())
expand_config(implicit, ExpandFunctions())
assert dict(implicit.items())["uae_sana2"] == "true"
```

Add a second case with `uae_rtc="MSM6242B"` and no `uae_sana2`, which must
give `"false"`. If `ImplicitConfig` needs other methods, read
`launcher/ui/config/model.py` and adapt `Values`.

**Commit:** `fix: keep an explicit uae_sana2 value`

---

## T4 - Send variant ratings off the UI thread

**Why it's worth it:** `ConfigurationsPanel.set_rating_for_variant` makes
an HTTP request to OpenRetro and writes SQLite on the Qt thread, freezing
the window. It breaks the UI-thread rule in `AGENTS.md`. Neither
`OGDClient.rate_variant` nor `OGDClient.post` sets a timeout.

**Files:** `launcher/ui/ConfigurationsPanel.py`, `fsgs/ogd/client.py`, new
`launcher/tests/test_variant_rating.py`.

**Pattern to copy:** the CD checksum worker in `fsgs/amiga/amigacontext.py`
(`threading.Thread(..., daemon=True)` plus `fsbc.application.call_after`).

**Steps:**
1. `fsgs/ogd/client.py`: add `timeout=30` to the `requests.get` in
   `rate_variant` and the `requests.post` in `post`.
2. `ConfigurationsPanel.py`: split `set_rating_for_variant` into:
   - a worker function that calls `OGDClient().rate_variant(...)` and
     catches `Exception` (print it with `traceback.print_exc()` and return
     without changing anything);
   - an apply function, run with `call_after`, that writes the `rating`
     table with `Database.instance()` and sets `__variant_rating`. The
     database object is per-thread, so it must be opened in this
     UI-thread function.
   Start the worker on a daemon thread. Keep the method name and its
   `@staticmethod` so callers don't change.
3. Delete the `# FIXME: Do asynchronously, add to queue` line.

**Tests:** monkeypatch `OGDClient.rate_variant` to return
`{"like": 5, "work": 4}`, replace `threading.Thread` in the module with a
fake that runs the target straight away, and replace `call_after` with a
function that calls its argument. Use a fake `Database.instance()` that records
`execute` calls. Assert the insert and `LauncherSettings.set("__variant_rating",
"5")` happen. Add a second test where `rate_variant` raises: no database
writes, no exception.

**Commit:** `fix: rate game variants off the UI thread`

---

## T5 - Find plugins on ARM64 (Apple Silicon, Raspberry Pi 4/5)

**Why it's worth it:** both `arch_name()` functions return "Unknown" on any
non-x86 machine, so plugins (including the FS-UAE emulator plugin) in
`<Plugin>/<OS>/ARM64/` are never found on Apple Silicon or 64-bit ARM Linux.
The build scripts already name this directory `ARM64` (`fsbuild/system.sh`,
`fsbuild/__init__.py`).

**Files:** `fsgs/plugins/pluginexecutablefinder.py`,
`fsgs/plugins/pluginmanager.py`, `fsbuild/__init__.py`, new
`fsgs/tests/test_plugin_arch.py`.

**Steps:**
1. In `pluginexecutablefinder.py` add
   `ARM64_MACHINES = ["arm64", "aarch64"]` beside `X86_ANY_MACHINES`, and in
   `arch_name()` return `"ARM64"` when `platform.machine().lower()` is in
   it. Delete the FIXME.
2. Do the same in `Plugin.arch_name()` in `pluginmanager.py`: return
   `"ARM64"` for both `pretty=True` and `pretty=False`, matching how
   `"x86-64"` is returned for both.
3. `fsbuild/__init__.py` `getArchitecture()`: return `"ARM64"` for
   `arm64` or `aarch64`, `"x86-64"` for `x86_64` or `amd64`, and otherwise
   raise `RuntimeError(f"Unsupported architecture: {machine}")`. Delete
   the FIXME. (32-bit ARM isn't built by CI; leave it out.)

**Tests:** parametrise over `platform.machine` values (`"x86_64"`,
`"AMD64"`, `"arm64"`, `"aarch64"`, `"mips"`) using `monkeypatch.setattr` on
the `platform` module used by each file. Check both `arch_name` functions;
for `x86_64` also patch `platform.architecture` to return `("64bit", "")`.
Check `getArchitecture()` in `fsbuild/tests/` (an existing test folder),
including the `RuntimeError`.

**Docs:** add one line to `docs/architecture.md` where plugin lookup is
described (search for "plugin"), saying the arch folders are `x86-64`,
`x86` and `ARM64`.

**Commit:** `fix: find ARM64 plugins on Apple Silicon and 64-bit ARM Linux`

---

## T6 - Disconnect option listeners when their widget is destroyed

**Why it's worth it:** `OptionsBehavior` (in
`launcher/ui/behaviors/__init__.py`) defines `on_destroy` but never connects
it, so a destroyed option widget keeps receiving config signals. The
sibling `PlatformBehavior` already connects it correctly.

**Files:** `launcher/ui/behaviors/__init__.py`, `fsui/test/test_qt6.py`.

**Steps:**
1. Replace `# FIXME: We need to disconnect the listener` with
   `parent.destroyed.connect(self.on_destroy)`, exactly as in
   `launcher/ui/behaviors/platformbehavior.py`.

**Tests** (in `fsui/test/test_qt6.py`, next to other option widget tests):
create a `QWidget`, attach `OptionsBehavior(widget, fake_options, ["x"])`
where `fake_options` records `add_listener`/`remove_listener`/`get`, then
`widget.deleteLater()` and process events (use the helper the file already
uses for this), and assert `remove_listener` was called.

**Commit:** `fix: disconnect option listeners when their widget is destroyed`

---

## T7 - One list of floppy extensions

**Why it's worth it:** three places hard-code floppy extensions and they
disagree. Zip archives are only searched for `.adf`/`.ipf`, and the check is
case-sensitive, so `GAME.ADF` or a `.dms` inside a zip isn't found, while
the command line accepts `.adf .ipf .dms .adz`.

**Files:** `fsgs/amiga/amiga.py`, `fsgs/amiga/amigacontext.py`,
`launcher/floppy_manager.py`, `launcher/launcherapp.py`, new
`launcher/tests/test_floppy_extensions.py`.

**Steps:**
1. In `class Amiga` (`fsgs/amiga/amiga.py`) add
   `FLOPPY_EXTENSIONS = (".adf", ".ipf", ".dms", ".adz")`.
2. In `amigacontext.py` and `floppy_manager.py`, replace
   `if ext in [".adf", ".ipf"]:` with
   `if ext.lower() in Amiga.FLOPPY_EXTENSIONS:` and delete the two-line FIXME.
   Check `Amiga` is imported; add `from fsgs.amiga.amiga import Amiga` if
   not, keeping imports in the existing style.
3. In `launcherapp.py`, replace the local
   `floppy_extensions = (".adf", ".ipf", ".dms", ".adz")` with
   `floppy_extensions = Amiga.FLOPPY_EXTENSIONS`.

**Tests:** build a zip in `tmp_path` holding `B.ADF`, `a.dms` and
`readme.txt`. Find the function that contains the zip loop in
`floppy_manager.py`, call it with the zip path (read it first to see what it
needs), and assert both disk images are found and sorted, and the text file
isn't.

**Docs:** in `README`, if floppy formats inside zip files are mentioned,
list all four.

**Commit:** `refactor: share one floppy extension list`

---

## T8 - Tell the user when saving a config without a name

**Why it's worth it:** with an empty config name, clicking Save does
nothing and gives no feedback.

**Files:** `launcher/ui/savebutton.py`, `launcher/tests/test_game_overrides.py`
(it already calls `SaveButton.save_config()`).

**Steps:**
1. In `save_config`, replace `# FIXME: notify user` with
   `fsui.show_error(gettext("Please enter a name for the configuration before saving."))`.
   Import `fsui` the same way other launcher UI modules do
   (`import fsui`). `gettext` is already imported.
2. Keep the `print("no config_name")` and the `return`.

**Tests:** in `test_game_overrides.py`, set the `config_name` setting to
`""`, monkeypatch `launcher.ui.savebutton.fsui.show_error` to record its
message, call `SaveButton.save_config()`, and assert it was called once and
no file was written.

**Commit:** `fix: explain why a config without a name is not saved`

---

## T9 - Use the system monospace font in text areas

**Why it's worth it:** `fsui.TextArea(font_family=...)` prints a FIXME on
every use and forces `QFont("Courier")`, which isn't installed on many Linux
systems. Every caller passes `font_family="monospace"` (About dialog,
Info dialog, Advanced Settings, Custom Options).

**Files:** `fsui/qt/TextArea.py`, `fsui/test/test_qt6.py`.

**Steps:**
1. Remove the print. Set the font to
   `QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)` when
   `font_family == "monospace"`, otherwise `QFont(font_family)`. Import
   `QFontDatabase` and `QFont` from `fsui.qt`, which already exports them
   (`fsui/qt/qt.py` uses `QFontDatabase`). Use qualified enum names
   (`AGENTS.md`).

**Tests:** next to the existing `fsui.TextArea(self.dialog)` test, create
`fsui.TextArea(self.dialog, font_family="monospace")` and assert
`QFontInfo(text.font()).fixedPitch()` is true.

**Commit:** `fix: use the system monospace font in text areas`

---

## T10 - Make read-only combo boxes read-only

**Why it's worth it:** `fsui.ComboBox(read_only=True)` ignores the flag,
prints a FIXME, and is always editable. The joystick device chooser in
`InputSelector.py` passes `read_only=True`, yet users can type random text
into it, and the typed text is never used.

**Files:** `fsui/qt/ComboBox.py`, `fsui/test/test_qt6.py`.

**Steps:**
1. Remove the print. Call `self.setEditable(not read_only)`. Only install
   the event filter on `self.lineEdit()` when the box is editable (it is
   `None` otherwise).
2. `get_text()`: return `self.currentText()` when not editable.
   `set_text(text)`: when not editable, select the matching item with
   `self.findText(text)` if it's found, and do nothing otherwise.
3. Check the other caller, `launcher/settings/joystick_settings_page.py`
   (`fsui.ComboBox(self, devices)`), still works. It isn't read-only, so it
   must stay editable.

**Tests:** in `test_qt6.py`, assert a `read_only=True` box has
`isEditable()` false, `get_text()` returns the current item, and
`set_text()` selects a listed item. Assert a default box is still editable.

**Commit:** `fix: honour read_only in fsui.ComboBox`

---

## T11 - Remove the unused vsync and display-mode switching code

**Why it's worth it:** seven FIXMEs (in `fsgs/refreshratetool.py` and the
Amiga driver's hard-coded 50 Hz) sit in code that never runs:
`GameDriver.configure_vsync` has no callers, `RefreshRateTool.set_best_mode`
has no callers, and `set_mode` is disabled. Only the current-refresh lookup
is used (by `GameDriver.screen_refresh_rate_for_monitor`, used in
`launcher/ui/launch.py` and tested in `launcher/tests/test_displays.py`).
Deleting the dead code removes the markers and about 200 lines of confusion.

**Files:** `fsgs/refreshratetool.py`, `fsgs/drivers/gamedriver.py`,
`fsgs/amiga/fsuaeamigadriver.py`.

**Steps:**
1. Before deleting anything, prove each symbol is unused with
   `git grep -n "<name>"` (excluding the definition):
   `configure_vsync`, `set_best_mode`, `calculate_mode_score`,
   `allow_vsync`, `get_display_refresh`, `get_all_modes`, `set_mode`,
   `_set_mode_windows`, `_set_mode_x`, `_get_all_modes_x`. Delete only
   the ones with no callers outside dead code. **Keep** everything reached
   from `screen_refresh_rate_for_monitor` (`get_current_mode`,
   `_get_current_mode_x`, `screens_xrandr`, `_screens_xrandr`, and their
   helpers) and `XRANDR_TEST_DATA` if a test uses it.
2. In `gamedriver.py`, delete `configure_vsync`. Keep
   `GameDriver.get_game_refresh_rate` only if something besides
   `configure_vsync` calls it; otherwise delete it too.
3. In `fsuaeamigadriver.py`, delete the `get_game_refresh_rate` override
   (with its FIXME) if step 2 removed the base method or nothing calls it.
4. Remove imports that are now unused (ruff will report them).
5. After deleting, `git grep -n FIXME fsgs/refreshratetool.py
   fsgs/amiga/fsuaeamigadriver.py` must print nothing. If a FIXME is in code
   that is still used, replace it with a plain comment saying what the code
   does.

**Tests:** no new tests. `launcher/tests/test_displays.py` and the
`screen_refresh_rate_for_monitor` patches in `fsui/test/test_qt6.py` must
still pass unchanged.

**Docs:** update `docs/dead-code-cleanup.md` with a short entry for the
removed functions.

**Commit:** `chore: remove unused vsync and display mode switching code`

---

## Not worth implementing

These markers were removed or turned into plain notes on
`chore/priority-5-fixme-triage`. The reasons are recorded here so they are
not raised again.

| Area | Reason |
|---|---|
| `launcher/ui/config/expand.py` "check value", "boolean", joystick-port, PPC, Blizzard RTC, missing gfx cards | Speculative questions about emulator behaviour with no failing case; unknown values already produce `f.warning`. Generator not in repo. |
| WHDLoad `;` in `write_startup_sequence` | The game database defines `;` as the command separator; no entry with a `;` inside a WHDLoad `CONFIG` value was found. Reworded as a note. |
| Snapshots `TODO` in `fsgs/saves.py`, `GameChangeHandler` TODO | Feature proposals with no UI or storage design. |
| `prepare_roms` rewrite, database "ugly hack" fallbacks, `SignalContext`, `FSGameSystemContext` naming/dependency notes, layout renames, `InteractiveLabel` | Refactoring wishes with no user-visible effect. |
| `launcher_config` "errors should be logged" | Already logged: stdout goes to the launcher log. |
| `connection_tester` "handle problem" | Already shows the error on the host entry. |
| `gamescanner` "log error", `fsbc/util` "Log warning" | Invalid data is already handled; extra logging would be noise. |
| Archive timestamps for extracted WHDLoad files, `.uaem` helper, `locker_uploader` streaming | Low impact and no reported problem. |
| `launcherwindow.find_icon` and the `set_icon_from_path` stub | The app icon is already set for all windows in `launcherapp.py`; the lookup was dead. Removed. |
| `ModelGroup(with_more_button=...)` | No caller passes it. Removed. |
| `Database.find_game_variants_new` "not looking up ratings" print | Both callers fill in ratings afterwards. Removed. |
| `option.py` `"FIXME"` descriptions | Replaced with real descriptions. |
| `__version` default `"FIXME"` in `launcher_config.py` | Never read; default is now `""`. |
| Setup wizard header colour, language "(automatic)" label, dialog Esc key | Minor polish on rarely used or feature-flagged UI. |
