# TODO and FIXME Inventory

This file is a review-only inventory of tracked `TODO` and `FIXME` markers in the repository.

## Priority 1 status

- **Status:** Complete.
- Removed unreferenced `use_smoothing` and `use_stretching` methods.
- Replaced duplicated floppy-drive loops with `Amiga.MAX_FLOPPY_DRIVES`.
- Removed confirmed stale Python 2-era comments and an empty cache marker.
- Removed a noisy dead-listener diagnostic and the obsolete `check_valid_name` no-op.
- Compatibility environment variables and legacy architecture notes were deliberately preserved.

## Priority 2 status

- **Status:** Complete.
- Explicit main and extension kickstart paths now calculate their ROM SHA-1.
- Cloanto/decrypted ROMs use `ChecksumTool.checksum_rom()`, the same ROM-aware
  checksum path used by the ROM panel and launch config loader.
- Internal ROM and URL kickstart values retain their existing special forms.
- Missing or unreadable ROM paths produce an empty SHA-1 instead of inventing
  a checksum, and errors are logged for diagnosis.

## WP1: CD checksum status

- **Status:** Complete.
- Single and multiple CD selections and loaded configurations resolve missing
  checksums on a worker, without the previous 64 MB limit for CD images.
- Scanned checksums are reused only when size and modification time match.
- Late results cannot overwrite an ejected or replaced CD. Missing/unreadable
  images leave the checksum empty and produce a diagnostic.
- Floppy extension centralization remains a separate task; unrelated import
  cycle comments were not changed.

## WP2: Archive stream status

- **Status:** Complete.
- Word-swapped reads support odd-sized requests, short source reads, and an
  unmatched final byte without assertions or premature EOF.
- Archive-looking directories remain directories, including when they contain
  a real archive. Existing archive member syntax is preserved.
- Non-actionable archive metadata API comments were removed without changing
  that API.

## Priority 5 status

- **Status:** Triage complete.
- Every remaining marker was checked against the code. Stale, speculative,
  already-handled and dead-code markers were removed or replaced with plain
  notes; dead icon lookup code and an unused `ModelGroup` parameter went
  with them.
- 25 source markers remain, all worth fixing. They are split into 11
  independent branches, each with steps and tests, in
  [fixme-implementation-plan.md](fixme-implementation-plan.md). Its
  "Not worth implementing" table records why the rest were dropped.
- The older review sections below describe the tree before this triage;
  the Entries list at the end is current.

## Scope

- **Tracked matches:** 35
- **Tracked files:** 21
- **Source:** `git grep -n -I -E '\b(TODO|FIXME)\b'` across tracked files, excluding this generated inventory and the implementation plan
- **Generated:** 2026-11-23
- **Updated:** 2026-11-25 for WP1 and WP2; 2026-11-26 for Priority 5 triage
- **Intentionally excluded:** untracked files, binaries excluded by `git grep -I`, dependency/environment directories such as `venv-*`, this inventory and `fixme-implementation-plan.md`

References in documentation are included as matches, but are not necessarily implementation markers. Inspect each entry before deciding whether it should be implemented, removed, or replanned.

## FIXME relevance and priority review

There are **204 source-level FIXME markers** and 15 TODO markers in the
tracked inventory. The source count is dominated by comments left in mature
code: many describe older implementation concerns, while some represent real
unfinished behavior. "Effort" below is implementation effort, including tests
and documentation where applicable.

### Recommended order

| Priority | Area | Recommendation | Effort | Benefit |
|---|---|---|---|---|
| 1 | Stale markers and dead compatibility shims | **Complete.** Removed confirmed stale comments, methods, and no-op code; preserved compatibility env vars and legacy architecture notes | Low | High maintenance clarity |
| 2 | Kickstart and ROM metadata | **Complete.** Explicit ROM paths now resolve to consistent SHA-1 metadata for netplay config sync | Medium | High |
| 3 | CD and floppy metadata | **CD checksums complete (WP1).** Floppy extension detection remains separate | Medium | High |
| 4 | Network and media error handling | Replace broad/default handling with visible, actionable errors and worker-thread-safe status updates | Medium | High |
| 5 | Archive and binary stream correctness | **Complete (WP2).** Correct odd/short reads and archive-vs-directory handling with regression tests | Medium | High |
| 6 | Async UI operations | Move rating and configuration rescans onto existing worker queue patterns, using `call_after` for UI updates | Medium | Medium |
| 7 | Amiga hardware/default selection | Replace assumptions for joystick ports, refresh rate, memory, expansions, and sound/network cards with explicit model/device validation | High | High |
| 8 | Save snapshots | Implement snapshot directory and timestamp support only if snapshot storage is an intended user feature | High | Medium |

### Clear removals or replans

- [gamedriver.py](../fsgs/drivers/gamedriver.py#L274) marks
  `use_smoothing()` and `use_stretching()` as removable. Repository search
  finds no calls to either method; remove both methods and their stale
  FIXME comments.
- [amigacontext.py](../fsgs/amiga/amigacontext.py#L9) has duplicate
  markers around fixed four-drive loops even though the Amiga class already
  defines `MAX_FLOPPY_IMAGES`; replan as one central drive-limit helper rather
  than isolated comments.
- [fsuaeamigadriver.py](../fsgs/amiga/fsuaeamigadriver.py#L131) says
  the code assumes PAL for some game configurations. This is an actual
  model/variant gap, not a comment-only cleanup.
- [fsbc/debug.py](../fsbc/debug.py#L55), [fsbc/signal.py](../fsbc/signal.py#L71),
  [launcher/filescanner.py](../launcher/filescanner.py#L371), and
  [fs-uae-launcher](../fs-uae-launcher#L40) contain Python 2-era or vague
  markers that describe work which is no longer applicable or lacks a concrete
  failure mode. Remove or replace them with code/specs.
- [fsbc/application.py](../fsbc/application.py#L113) is an empty FIXME
  beside cache directory code. It has no actionable requirement and should
  be removed unless XDG cache conventions are now in scope.
- [application.py](../fsbc/application.py#L135),
  [paths.py](../fsbc/paths.py#L44), [logging.py](../fsbc/logging.py#L53),
  and [settings.py](../fsbc/settings.py#L244) are legacy architecture
  notes. None proves an active bug; retain only if a concrete migration or
  behavior change is accepted.
- [gamedriver.py](../fsgs/drivers/gamedriver.py#L588) has FIXME comments
  beside legacy window-centering environment variables. Existing tests assert
  `SDL_VIDEO_WINDOW_POS`, so these variables remain compatibility-sensitive.
  Preserve their behavior; replace stale comments only after checking which
  variables are still consumed by the supported FS-UAE emulator.
- [fsuaeamigadriver.py](../fsgs/amiga/fsuaeamigadriver.py#L21) and
  [fsuaeamigadriver.py](../fsgs/amiga/fsuaeamigadriver.py#L37) use
  placeholder labels for missing devices/ports. These should become explicit
  option vocabulary or be removed if no UI/config path exposes them.

### Real implementation gaps

#### High benefit

1. **ROM and file checksum metadata** - The netplay sync allowlist includes
   kickstart and file SHA-1 keys, and
   [launcher_config.py](../launcher/launcher_config.py#L365) leaves checksum
   paths incomplete when a configured kickstart or extension ROM is already
   specified. Implement resolution and tests for explicit, internal, and
   Cloanto-provided ROM cases.
2. **CD checksum calculation — complete (WP1).** Single/multiple selections
   and loaded configurations use background checksum resolution, with
   regression tests for cache reuse, failures and stale worker results.
3. **Archive stream correctness — complete (WP2).** Word-swapped reads retain
   split words across calls, and archive-looking directories are not split
   into archive member paths.
4. **Model-specific hardware validation** - The highest-density cluster is
   [expand.py](../launcher/ui/config/expand.py), with unchecked values,
   ambiguous defaults, joystick mappings, memory behavior, and unsupported
   cards. Treat this as a feature/validation backlog rather than 25 separate
   code comments.
5. **Refresh-rate assumptions** - [fsuaeamigadriver.py](../fsgs/amiga/fsuaeamigadriver.py#L131)
   and [refreshratetool.py](../fsgs/refreshratetool.py) need explicit
   PAL/NTSC/monitor behavior, not a FIXME cleanup.
6. **WHDLoad option parsing** - [launchhandler.py](../fsgs/amiga/launchhandler.py#L944)
   splits startup sequences on semicolons, but semicolons may belong inside
   WHDLoad `CONFIG` values. This can change launched game configuration and
   should have a focused regression fixture.

#### Medium benefit

- Finish or remove the `FIXME: handle problem` branch in
  [connection_tester.py](../launcher/netplay/connection_tester.py#L92);
  it already presents a host error, but exception presentation should be
  stable and covered.
- Replace direct settings writes and thread comments in
  [update_manager.py](../launcher/update_manager.py#L56) with the existing
  signal path as the documented UI boundary.
- Move warnings and settings-page navigation out of the status bar
  [WarningsElement.py](../launcher/ui/statusbar/WarningsElement.py#L368), but
  this is architecture cleanup, not a user-visible fix.
- Move OGD rating writes off the Qt/UI path in
  [ConfigurationsPanel.py](../launcher/ui/ConfigurationsPanel.py#L195),
  preserving existing database semantics.
- Add missing asynchronous rescans in
  [download.py](../launcher/ui/download.py#L168) and
  [database_refresh.py](../launcher/database_refresh.py#L54) only if the
  synchronous network/database work is perceptibly blocking the UI.
- Finish [gamechanges](../fsgs/GameChangeHandler.py#L5) by deciding whether
  save metadata belongs in the change handler; otherwise remove or reword the
  TODO so it records a roadmap, not implementation debt.

### Likely no-action items

The following markers should remain unimplemented unless requirements change:

- Snapshot support in [saves.py](../fsgs/saves.py#L11); no snapshot UI or
  storage format is present.
- [whdload-support.md](../docs/whdload-support.md#L65) UUID launch documentation
  unless UUID launching is being promoted as supported behavior.
- "Add more documentation" in
  [fs_uae_launcher.py](../launcher/apps/fs_uae_launcher.py#L77); replace with
  targeted docs only after API behavior is stabilized.
- [FIXME inventory](todo-fixme-inventory.md) documentation references and
  prose quotations are search hits, not implementation tasks.

### TODO review

- The Python/dependency modernization queue is the only broad, actionable
  TODO document. It should be maintained as an implementation queue only after
  CI support claims are separated from local validation claims.
- `GameChangeHandler` needs a requirement decision before implementation.
- `saves.py` snapshot support is a feature proposal, not a bug fix.
- The launcher bootstrap documentation marker is low-value and can be removed
  once user-facing launcher documentation is covered elsewhere.

## Entries

### `.github/copilot-instructions.md`

- [L16](../.github/copilot-instructions.md#L16) — **TODO** — <code>| Python/dependency TODO | [docs/python-dependency-modernization.md](/docs/python-dependency-modernization.md) |</code>

### `AGENTS.md`

- [L16](../AGENTS.md#L16) — **TODO** — <code>| Python/dependency TODO | [docs/python-dependency-modernization.md](/docs/python-dependency-modernization.md) |</code>

### `ChangeLog`

- [L124](../ChangeLog#L124) — **FIXME** — <code>FIXME: Not in all dialogs yet.</code>
- [L126](../ChangeLog#L126) — **FIXME** — <code>FIXME: GUI does not update yet.</code>

### `README`

- [L102](../README#L102) — **TODO** — <code>See [the Python and dependency modernization TODO](docs/python-dependency-modernization.md)</code>

### `docs/netplay-go-server-design.md`

- [L88](./netplay-go-server-design.md#L88) — **FIXME** — <code>This was found in the field, not by reading: the launcher&#x27;s Host Game button builds &#96;/hostgame &lt;host&gt;:&lt;port&gt; &lt;players&gt;&#96; with no password (&#96;netplay_panel.py&#96;), so every game hosted that way was rejected with &#96;ERROR_WRONG_PASSWORD&#96; — and because &#96;fs_emu_netplay_on_disconnect&#96; warns and then continues in offline mode (&#96;netplay.c:270&#96;, its own &#96;FIXME&#96;), both emulators ran *separate local games* that looked like netplay with no input ever relayed. Checked against &#96;game.py&#96; side by side afterwards, both started exactly as &#96;Server.start()&#96; does with no &#96;--password&#96; and both clients sending four zero bytes: Python joined both players and relayed both input events, and the Go server now does the same. The offline-mode fallback itself is unchanged pre-existing client behaviour, reachable against either server on any handshake rejection or mid-game disconnect; it only became visible because the server was rejecting everyone.</code>
- [L199](./netplay-go-server-design.md#L199) — **FIXME** — <code>| **W1** | **One failure ends the game for everyone.** A client thread exception sets &#96;game.stop&#96;. A client that disconnects returns silently from &#96;receive_loop&#96; (the &#96;# FIXME&#96;), stays in &#96;clients[]&#96; with &#96;playing=True&#96;, and the next &#96;sendall&#96; to its dead socket raises inside the game loop — same outcome. | &#96;game.py:280-282&#96;, &#96;game.py:294-296&#96; |</code>
- [L343](./netplay-go-server-design.md#L343) — **FIXME** — <code>Same semantics as today — checks tagged with the client&#x27;s last-acked frame (they arrive *before* the ack, see the per-frame sequence above), verified once every client has passed it — but run on the game goroutine, so &quot;once per frame, not once per client&quot; (the existing FIXME) holds by construction. On mismatch, log every player&#x27;s value for the offending frame, broadcast the desync error, and shut that game down cleanly without touching others.</code>
- [L562](./netplay-go-server-design.md#L562) — **FIXME** — <code>5. **Build the single-game server. — done.** &#96;fsnp-server/internal/game&#96; plus &#96;cmd/fsnp-server&#96;. One goroutine owns the game; per-connection reader and writer goroutines talk to it over channels; a deadline ticker drives the 20 ms frame (see step 6 for why it isn&#x27;t &#96;time.Ticker&#96;); writers cap each socket write at 1,400 bytes. Feature-matched against &#96;game.py&#96; — same handshake responses and error codes, &#96;SESSION_KEY&#96;/&#96;PLAYERS&#96;/tags-at-join then tags-at-start, status at frame 0 and every 100, ping every 10 (never re-sent while one is outstanding), 100-entry auto-flush, input echo to all, &#96;TEXT&#96; broadcast, check-before-ack attribution, the drift stall at 25 frames that waits for *every* player to reach the current frame — verified against the capture over &#96;net.Pipe()&#96; and again over real TCP with the binary (400 frames in 8.03 s, &#96;PONG&#96; probe, SIGTERM → &#96;ERROR_GAME_STOPPED&#96; → exit 0). Deliberate departures from &#96;game.py&#96;, each a test: (a) **the sync check verifies every frame** — &#96;game.py&#96;&#x27;s &#96;__check_game&#96; advanced &#96;verified_frame&#96; even when &#96;check_synchronization&#96; bailed out because the slowest player was still *at* that frame, so in steady state it checked almost nothing; the Go version verifies tag *k* once every player is past it, and the captured session still yields zero mismatches under that rule. (b) **A player leaving before the game starts frees its slot** instead of leaving a dead socket in &#96;clients[]&#96; for the first tick to trip over; after start, a loss broadcasts &#96;TEXT&#96; &quot;&#96;&lt;tag&gt; disconnected&#96;&quot; then &#96;ERROR_GAME_STOPPED&#96; and the game ends cleanly (rejoin, phase four, would add a grace window). (c) **Rejoin with a valid session key is refused with &#96;ERROR_CANNOT_RESUME&#96; even when &#96;resume-from-packet&#96; is 0** — &#96;game.py&#96; swapped the connection in without transferring any state (its own &#96;FIXME&#96;), which can&#x27;t have worked; the client never sends this today. (d) &#96;--launch-timeout&#96; counts from process start, not from the last connection (W6). (e) Inbound &#96;TEXT&#96; is capped at 1 KB and the handshake has a 5 s deadline (W9). &#96;main.go&#96; takes the same &#96;--port/--players/--password/--launch-timeout&#96; flags as &#96;game.py&#96; (&#96;PORT&#96;/&#96;PLAYERS&#96;/&#96;PASSWORD&#96; env for Docker), prints &#96;{&quot;event&quot;:&quot;listening&quot;,&quot;port&quot;:N}&#96; on stdout, and has an opt-in &#96;--exit-on-stdin-close&#96; for the launcher to use in step 7.</code>

### `docs/python-dependency-modernization.md`

- [L1](./python-dependency-modernization.md#L1) — **TODO** — <code># Python and Dependency Modernization TODO</code>

### `fsbuild/__init__.py`

- [L112](../fsbuild/__init__.py#L112) — **FIXME** — <code>arch = &quot;x86-64&quot;  # FIXME</code>

### `fsgs/amiga/amigacontext.py`

- [L210](../fsgs/amiga/amigacontext.py#L210) — **FIXME** — <code># FIXME: get list of floppy extensions from a central</code>

### `fsgs/amiga/fsuaeamigadriver.py`

- [L129](../fsgs/amiga/fsuaeamigadriver.py#L129) — **FIXME** — <code># FIXME: Now assuming that all games are PAL / 50 Hz</code>

### `fsgs/ogd/GameDatabaseSynchronizer.py`

- [L303](../fsgs/ogd/GameDatabaseSynchronizer.py#L303) — **FIXME** — <code># FIXME: change second {0} to {1}</code>
- [L328](../fsgs/ogd/GameDatabaseSynchronizer.py#L328) — **FIXME** — <code># FIXME: change second {0} to {1}</code>

### `fsgs/ogd/base.py`

- [L55](../fsgs/ogd/base.py#L55) — **FIXME** — <code># FIXME: change second {0} to {1}</code>
- [L80](../fsgs/ogd/base.py#L80) — **FIXME** — <code># FIXME: change second {0} to {1}</code>

### `fsgs/plugins/pluginexecutablefinder.py`

- [L189](../fsgs/plugins/pluginexecutablefinder.py#L189) — **FIXME** — <code># FIXME: arm7/8 and ARM64</code>

### `fsgs/refreshratetool.py`

- [L82](../fsgs/refreshratetool.py#L82) — **FIXME** — <code># FIXME: configurable?</code>
- [L83](../fsgs/refreshratetool.py#L83) — **FIXME** — <code># FIXME: configurable per platform?</code>
- [L122](../fsgs/refreshratetool.py#L122) — **FIXME** — <code># FIXME: configurable?</code>
- [L123](../fsgs/refreshratetool.py#L123) — **FIXME** — <code># FIXME: configurable per platform?</code>
- [L176](../fsgs/refreshratetool.py#L176) — **FIXME** — <code>&quot;FIXME: Not calling Quartz.CGDisplayModeRelease(&quot;</code>
- [L219](../fsgs/refreshratetool.py#L219) — **FIXME** — <code># FIXME:</code>
- [L226](../fsgs/refreshratetool.py#L226) — **FIXME** — <code>print(&quot;FIXME: Currently disabled set_mode&quot;)</code>

### `fsui/qt/ComboBox.py`

- [L10](../fsui/qt/ComboBox.py#L10) — **FIXME** — <code>&quot;FIXME: ComboBox not respecting read_only&quot;</code>

### `fsui/qt/TextArea.py`

- [L18](../fsui/qt/TextArea.py#L18) — **FIXME** — <code>print(&quot;FIXME: not respecting font_family yet&quot;)</code>

### `launcher/floppy_manager.py`

- [L55](../launcher/floppy_manager.py#L55) — **FIXME** — <code># FIXME: get list of floppy extensions from a central</code>

### `launcher/ui/ConfigurationsPanel.py`

- [L195](../launcher/ui/ConfigurationsPanel.py#L195) — **FIXME** — <code># FIXME: Do asynchronously, add to queue</code>

### `launcher/ui/behaviors/__init__.py`

- [L18](../launcher/ui/behaviors/__init__.py#L18) — **FIXME** — <code># FIXME: We need to disconnect the listener</code>

### `launcher/ui/config/expand.py`

- [L1667](../launcher/ui/config/expand.py#L1667) — **FIXME** — <code># FIXME: ok? keep already specified value</code>
- [L1669](../launcher/ui/config/expand.py#L1669) — **FIXME** — <code># FIXME: match and normalize uae boolean</code>

### `launcher/ui/savebutton.py`

- [L43](../launcher/ui/savebutton.py#L43) — **FIXME** — <code># FIXME: notify user</code>

### `launcher/update_manager.py`

- [L56](../launcher/update_manager.py#L56) — **FIXME** — <code># FIXME: Thread safety...</code>
- [L57](../launcher/update_manager.py#L57) — **FIXME** — <code># FIXME: Use above signal instead</code>
