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

## Scope

- **Tracked matches:** 225
- **Tracked files:** 95
- **Source:** `git grep -n -I -E '\b(TODO|FIXME)\b'` across tracked files, excluding this generated inventory
- **Generated:** 2026-11-23
- **Intentionally excluded:** untracked files, binaries excluded by `git grep -I`, dependency/environment directories such as `venv-*`, and this inventory itself

References in documentation are included as matches, but are not necessarily implementation markers. Inspect each entry before deciding whether it should be implemented, removed, or replanned.

## FIXME relevance and priority review

There are **210 source-level FIXME markers** and 15 TODO markers in the
tracked inventory. The source count is dominated by comments left in mature
code: many describe older implementation concerns, while some represent real
unfinished behavior. "Effort" below is implementation effort, including tests
and documentation where applicable.

### Recommended order

| Priority | Area | Recommendation | Effort | Benefit |
|---|---|---|---|---|
| 1 | Stale markers and dead compatibility shims | **Complete.** Removed confirmed stale comments, methods, and no-op code; preserved compatibility env vars and legacy architecture notes | Low | High maintenance clarity |
| 2 | Kickstart and ROM metadata | **Complete.** Explicit ROM paths now resolve to consistent SHA-1 metadata for netplay config sync | Medium | High |
| 3 | CD and floppy metadata | Calculate CD checksums and centralize floppy extension detection | Medium | High |
| 4 | Network and media error handling | Replace broad/default handling with visible, actionable errors and worker-thread-safe status updates | Medium | High |
| 5 | Archive and binary stream correctness | Handle odd reads and archive-vs-directory ambiguity; add corruption and malformed-path tests | Medium | High |
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
2. **CD checksum calculation** - [cd_manager.py](../launcher/cd_manager.py#L46)
   explicitly inserts CDs with an empty checksum. Netplay and file database
   lookup can be unable to identify the media. Use the existing checksum
   facility and add success/failure tests.
3. **Archive safety** - [archive.py](../fsgs/archive.py#L255) asserts after
   word-swapping reads and [archive.py](../fsgs/archive.py#L293) can
   interpret a directory name as an archive subpath. Replace assertions with
   bounded validation and tests.
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

### `docs/dead-code-cleanup.md`

- [L106](./dead-code-cleanup.md#L106) — **FIXME** — <code>- the ROM and Workbench file name labels, and the &#96;FIXME: Files to clean up&#96; path list in &#96;launcherapp.py&#96;</code>

### `docs/netplay-go-server-design.md`

- [L88](./netplay-go-server-design.md#L88) — **FIXME** — <code>This was found in the field, not by reading: the launcher&#x27;s Host Game button builds &#96;/hostgame &lt;host&gt;:&lt;port&gt; &lt;players&gt;&#96; with no password (&#96;netplay_panel.py&#96;), so every game hosted that way was rejected with &#96;ERROR_WRONG_PASSWORD&#96; — and because &#96;fs_emu_netplay_on_disconnect&#96; warns and then continues in offline mode (&#96;netplay.c:270&#96;, its own &#96;FIXME&#96;), both emulators ran *separate local games* that looked like netplay with no input ever relayed. Checked against &#96;game.py&#96; side by side afterwards, both started exactly as &#96;Server.start()&#96; does with no &#96;--password&#96; and both clients sending four zero bytes: Python joined both players and relayed both input events, and the Go server now does the same. The offline-mode fallback itself is unchanged pre-existing client behaviour, reachable against either server on any handshake rejection or mid-game disconnect; it only became visible because the server was rejecting everyone.</code>
- [L199](./netplay-go-server-design.md#L199) — **FIXME** — <code>| **W1** | **One failure ends the game for everyone.** A client thread exception sets &#96;game.stop&#96;. A client that disconnects returns silently from &#96;receive_loop&#96; (the &#96;# FIXME&#96;), stays in &#96;clients[]&#96; with &#96;playing=True&#96;, and the next &#96;sendall&#96; to its dead socket raises inside the game loop — same outcome. | &#96;game.py:280-282&#96;, &#96;game.py:294-296&#96; |</code>
- [L343](./netplay-go-server-design.md#L343) — **FIXME** — <code>Same semantics as today — checks tagged with the client&#x27;s last-acked frame (they arrive *before* the ack, see the per-frame sequence above), verified once every client has passed it — but run on the game goroutine, so &quot;once per frame, not once per client&quot; (the existing FIXME) holds by construction. On mismatch, log every player&#x27;s value for the offending frame, broadcast the desync error, and shut that game down cleanly without touching others.</code>
- [L562](./netplay-go-server-design.md#L562) — **FIXME** — <code>5. **Build the single-game server. — done.** &#96;fsnp-server/internal/game&#96; plus &#96;cmd/fsnp-server&#96;. One goroutine owns the game; per-connection reader and writer goroutines talk to it over channels; a deadline ticker drives the 20 ms frame (see step 6 for why it isn&#x27;t &#96;time.Ticker&#96;); writers cap each socket write at 1,400 bytes. Feature-matched against &#96;game.py&#96; — same handshake responses and error codes, &#96;SESSION_KEY&#96;/&#96;PLAYERS&#96;/tags-at-join then tags-at-start, status at frame 0 and every 100, ping every 10 (never re-sent while one is outstanding), 100-entry auto-flush, input echo to all, &#96;TEXT&#96; broadcast, check-before-ack attribution, the drift stall at 25 frames that waits for *every* player to reach the current frame — verified against the capture over &#96;net.Pipe()&#96; and again over real TCP with the binary (400 frames in 8.03 s, &#96;PONG&#96; probe, SIGTERM → &#96;ERROR_GAME_STOPPED&#96; → exit 0). Deliberate departures from &#96;game.py&#96;, each a test: (a) **the sync check verifies every frame** — &#96;game.py&#96;&#x27;s &#96;__check_game&#96; advanced &#96;verified_frame&#96; even when &#96;check_synchronization&#96; bailed out because the slowest player was still *at* that frame, so in steady state it checked almost nothing; the Go version verifies tag *k* once every player is past it, and the captured session still yields zero mismatches under that rule. (b) **A player leaving before the game starts frees its slot** instead of leaving a dead socket in &#96;clients[]&#96; for the first tick to trip over; after start, a loss broadcasts &#96;TEXT&#96; &quot;&#96;&lt;tag&gt; disconnected&#96;&quot; then &#96;ERROR_GAME_STOPPED&#96; and the game ends cleanly (rejoin, phase four, would add a grace window). (c) **Rejoin with a valid session key is refused with &#96;ERROR_CANNOT_RESUME&#96; even when &#96;resume-from-packet&#96; is 0** — &#96;game.py&#96; swapped the connection in without transferring any state (its own &#96;FIXME&#96;), which can&#x27;t have worked; the client never sends this today. (d) &#96;--launch-timeout&#96; counts from process start, not from the last connection (W6). (e) Inbound &#96;TEXT&#96; is capped at 1 KB and the handshake has a 5 s deadline (W9). &#96;main.go&#96; takes the same &#96;--port/--players/--password/--launch-timeout&#96; flags as &#96;game.py&#96; (&#96;PORT&#96;/&#96;PLAYERS&#96;/&#96;PASSWORD&#96; env for Docker), prints &#96;{&quot;event&quot;:&quot;listening&quot;,&quot;port&quot;:N}&#96; on stdout, and has an opt-in &#96;--exit-on-stdin-close&#96; for the launcher to use in step 7.</code>

### `docs/python-dependency-modernization.md`

- [L1](./python-dependency-modernization.md#L1) — **TODO** — <code># Python and Dependency Modernization TODO</code>

### `docs/whdload-support.md`

- [L65](./whdload-support.md#L65) — **FIXME** — <code>FIXME: Write about launching games using game / variant UUIDs.</code>

### `fsbc/application.py`

- [L134](../fsbc/application.py#L134) — **FIXME** — <code># FIXME: $XDG_DATA_DIRS, $XDG_DATA_HOME</code>

### `fsbc/logging.py`

- [L53](../fsbc/logging.py#L53) — **FIXME** — <code># FIXME: legacy hack, should be removed in the future</code>

### `fsbc/paths.py`

- [L44](../fsbc/paths.py#L44) — **FIXME** — <code># FIXME: $base_dir is deprecated</code>
- [L156](../fsbc/paths.py#L156) — **FIXME** — <code># FIXME: could be an idea to always normalize to NFC on OS X too,</code>

### `fsbc/settings.py`

- [L167](../fsbc/settings.py#L167) — **FIXME** — <code># FIXME: Should be moved to subclass</code>
- [L244](../fsbc/settings.py#L244) — **FIXME** — <code># FIXME: FS-UAE Launcher specific</code>
- [L255](../fsbc/settings.py#L255) — **FIXME** — <code># FIXME: FS-UAE Launcher specific</code>

### `fsbc/signal.py`

- [L31](../fsbc/signal.py#L31) — **FIXME** — <code># FIXME: temporary hack for legacy code</code>
- [L34](../fsbc/signal.py#L34) — **FIXME** — <code># FIXME: temporary hack for legacy code</code>
- [L37](../fsbc/signal.py#L37) — **FIXME** — <code># FIXME: temporary hack for legacy code</code>

### `fsbc/util.py`

- [L35](../fsbc/util.py#L35) — **FIXME** — <code># FIXME: Log warning here</code>
- [L46](../fsbc/util.py#L46) — **FIXME** — <code># FIXME: Log warning here</code>
- [L47](../fsbc/util.py#L47) — **FIXME** — <code># FIXME: will not happen here.. se above type error?</code>

### `fsboot/__init__.py`

- [L340](../fsboot/__init__.py#L340) — **FIXME** — <code># FIXME: Document option</code>

### `fsbuild/__init__.py`

- [L112](../fsbuild/__init__.py#L112) — **FIXME** — <code>arch = &quot;x86-64&quot;  # FIXME</code>

### `fsbuild/plugin.pre.sh`

- [L18](../fsbuild/plugin.pre.sh#L18) — **FIXME** — <code># FIXME: Deprecate $EXE (Use $SYSTEM_EXE instead)</code>

### `fsbuild/standalone.py`

- [L93](../fsbuild/standalone.py#L93) — **FIXME** — <code># FIXME: Print warning if excluded libraries is not in this list?</code>

### `fsbuild/system.sh`

- [L26](../fsbuild/system.sh#L26) — **FIXME** — <code># FIXME: Deprecated alias</code>

### `fsgs/Config.py`

- [L73](../fsgs/Config.py#L73) — **FIXME** — <code># FIXME: re-introduce support for key priority if necessary</code>

### `fsgs/Database.py`

- [L116](../fsgs/Database.py#L116) — **FIXME** — <code>print(&quot;FIXME: not looking up ratings yet!&quot;)</code>

### `fsgs/FSGameSystemContext.py`

- [L36](../fsgs/FSGameSystemContext.py#L36) — **FIXME** — <code># FIXME: check_sha1 should check with PluginManager directly?</code>
- [L88](../fsgs/FSGameSystemContext.py#L88) — **FIXME** — <code># FIXME: check_sha1 should check with PluginManager directly?</code>
- [L99](../fsgs/FSGameSystemContext.py#L99) — **FIXME** — <code># FIXME: better name</code>
- [L166](../fsgs/FSGameSystemContext.py#L166) — **FIXME** — <code># FIXME: custom exception here</code>
- [L326](../fsgs/FSGameSystemContext.py#L326) — **FIXME** — <code># FIXME</code>
- [L340](../fsgs/FSGameSystemContext.py#L340) — **FIXME** — <code># FIXME: remove dependency</code>
- [L364](../fsgs/FSGameSystemContext.py#L364) — **FIXME** — <code># FIXME: Merge code with VariantsBrowser.py</code>
- [L376](../fsgs/FSGameSystemContext.py#L376) — **FIXME** — <code># FIXME: name replacement needed any more?</code>
- [L454](../fsgs/FSGameSystemContext.py#L454) — **FIXME** — <code># FIXME: REMOVE? use config[game_name] instead?</code>
- [L456](../fsgs/FSGameSystemContext.py#L456) — **FIXME** — <code># FIXME: REMOVE? use config[game_uuid] instead?</code>

### `fsgs/GameChangeHandler.py`

- [L5](../fsgs/GameChangeHandler.py#L5) — **TODO** — <code># TODO: review the algorithm and add support for saving information about</code>

### `fsgs/LockerDatabase.py`

- [L5](../fsgs/LockerDatabase.py#L5) — **FIXME** — <code># FIXME: remove dependency on launcher, have the Launcher tell this class</code>
- [L33](../fsgs/LockerDatabase.py#L33) — **FIXME** — <code># FIXME: Replace with EXISTS or something</code>

### `fsgs/SignalContext.py`

- [L37](../fsgs/SignalContext.py#L37) — **FIXME** — <code># FIXME: use fsgs-context-instance-specific signals</code>
- [L49](../fsgs/SignalContext.py#L49) — **FIXME** — <code># FIXME: Deprecated</code>

### `fsgs/amiga/amiga.py`

- [L20](../fsgs/amiga/amiga.py#L20) — **FIXME** — <code># FIXME: setting fake checksum, for now</code>

### `fsgs/amiga/amigacontext.py`

- [L56](../fsgs/amiga/amigacontext.py#L56) — **FIXME** — <code>print(&quot;FIXME: not calculating CD checksum just yet&quot;)</code>
- [L75](../fsgs/amiga/amigacontext.py#L75) — **FIXME** — <code># FIXME: get list of floppy extensions from a central</code>
- [L126](../fsgs/amiga/amigacontext.py#L126) — **FIXME** — <code># FIXME: dependency loop</code>
- [L130](../fsgs/amiga/amigacontext.py#L130) — **FIXME** — <code># FIXME: dependency loop</code>
- [L134](../fsgs/amiga/amigacontext.py#L134) — **FIXME** — <code># FIXME: dependency loop</code>
- [L138](../fsgs/amiga/amigacontext.py#L138) — **FIXME** — <code># FIXME: dependency loop</code>
- [L142](../fsgs/amiga/amigacontext.py#L142) — **FIXME** — <code># FIXME: dependency loop</code>
- [L146](../fsgs/amiga/amigacontext.py#L146) — **FIXME** — <code># FIXME: dependency loop</code>

### `fsgs/amiga/fsuaeamigadriver.py`

- [L21](../fsgs/amiga/fsuaeamigadriver.py#L21) — **FIXME** — <code># FIXME: NO_DEVICE</code>
- [L37](../fsgs/amiga/fsuaeamigadriver.py#L37) — **FIXME** — <code># FIXME: ADDITIONAL PORTS...</code>
- [L131](../fsgs/amiga/fsuaeamigadriver.py#L131) — **FIXME** — <code># FIXME: Now assuming that all games are PAL / 50 Hz</code>

### `fsgs/amiga/launchhandler.py`

- [L269](../fsgs/amiga/launchhandler.py#L269) — **FIXME** — <code># FIXME: prepare_roms should be rewritten, it&#x27;s kind of crap.</code>
- [L452](../fsgs/amiga/launchhandler.py#L452) — **FIXME** — <code># FIXME: Try to get this to work with the PyCharm type checker</code>
- [L592](../fsgs/amiga/launchhandler.py#L592) — **FIXME** — <code># FIXME: This is an ugly hack, we should already be told what</code>
- [L608](../fsgs/amiga/launchhandler.py#L608) — **FIXME** — <code># FIXME: This is an ugly hack, we should already be told what</code>
- [L944](../fsgs/amiga/launchhandler.py#L944) — **FIXME** — <code># FIXME: semi-colon is used in WHDLoad CONFIG options...</code>
- [L1162](../fsgs/amiga/launchhandler.py#L1162) — **FIXME** — <code># FIXME: Extract real timestamps from archive</code>
- [L1163](../fsgs/amiga/launchhandler.py#L1163) — **FIXME** — <code># FIXME: Real metadata from archive</code>
- [L1396](../fsgs/amiga/launchhandler.py#L1396) — **FIXME** — <code># FIXME: handle &quot;&quot; around slave name?</code>

### `fsgs/amiga/valueconfigloader.py`

- [L1](../fsgs/amiga/valueconfigloader.py#L1) — **FIXME** — <code># FIXME: send fsgs as parameter to ValueConfigLoader instead</code>
- [L234](../fsgs/amiga/valueconfigloader.py#L234) — **FIXME** — <code># FIXME: print warning</code>
- [L278](../fsgs/amiga/valueconfigloader.py#L278) — **FIXME** — <code># FIXME: handle</code>
- [L382](../fsgs/amiga/valueconfigloader.py#L382) — **FIXME** — <code># FIXME: hack for now</code>
- [L421](../fsgs/amiga/valueconfigloader.py#L421) — **FIXME** — <code>#  FIXME: handle it with a visible error message</code>

### `fsgs/amiga/whdload.py`

- [L129](../fsgs/amiga/whdload.py#L129) — **FIXME** — <code># FIXME: Should MAG be included?</code>

### `fsgs/archive.py`

- [L39](../fsgs/archive.py#L39) — **FIXME** — <code># FIXME: getinfo needs to work for everything (return dummy data if necessary)</code>
- [L186](../fsgs/archive.py#L186) — **FIXME** — <code># FIXME: Should instead add getinfo to LhaFile...</code>
- [L255](../fsgs/archive.py#L255) — **FIXME** — <code># FIXME: Support odd length reads</code>
- [L293](../fsgs/archive.py#L293) — **FIXME** — <code># FIXME: should also check that it isn&#x27;t a dir</code>

### `fsgs/download.py`

- [L107](../fsgs/download.py#L107) — **FIXME** — <code># FIXME: Also find files from file database / plugins</code>
- [L134](../fsgs/download.py#L134) — **FIXME** — <code># FIXME: Atomic copy utility function?</code>

### `fsgs/drivers/gamedriver.py`

- [L31](../fsgs/drivers/gamedriver.py#L31) — **FIXME** — <code># FIXME: Store warning and show in some kind of launch log</code>
- [L133](../fsgs/drivers/gamedriver.py#L133) — **FIXME** — <code># FIXME: MOVE TO Port CONSTRUCTOR</code>
- [L139](../fsgs/drivers/gamedriver.py#L139) — **FIXME** — <code># FIXME: MOVE CODE TO port CLASS</code>
- [L433](../fsgs/drivers/gamedriver.py#L433) — **FIXME** — <code># FIXME: create new API fsgc.file.path(file_uri), returns path</code>
- [L584](../fsgs/drivers/gamedriver.py#L584) — **FIXME** — <code># FIXME: REMOVE</code>
- [L588](../fsgs/drivers/gamedriver.py#L588) — **FIXME** — <code># FIXME: REMOVE</code>
- [L804](../fsgs/drivers/gamedriver.py#L804) — **FIXME** — <code># FIXME: if development_mode ?</code>
- [L869](../fsgs/drivers/gamedriver.py#L869) — **FIXME** — <code># FIXME: remove</code>

### `fsgs/filedatabase.py`

- [L134](../fsgs/filedatabase.py#L134) — **FIXME** — <code># FIXME: Is the count necessary? ref query below, or do we</code>

### `fsgs/input/inputdevice.py`

- [L137](../fsgs/input/inputdevice.py#L137) — **FIXME** — <code># FIXME: fix dependency</code>

### `fsgs/ogd/GameDatabaseSynchronizer.py`

- [L118](../fsgs/ogd/GameDatabaseSynchronizer.py#L118) — **FIXME** — <code>version_node.text = &quot;2000-01-01&quot;  # FIXME</code>
- [L303](../fsgs/ogd/GameDatabaseSynchronizer.py#L303) — **FIXME** — <code># FIXME: change second {0} to {1}</code>
- [L328](../fsgs/ogd/GameDatabaseSynchronizer.py#L328) — **FIXME** — <code># FIXME: change second {0} to {1}</code>

### `fsgs/ogd/base.py`

- [L6](../fsgs/ogd/base.py#L6) — **FIXME** — <code># FIXME: Overlap in code/functionality with GameDatabaseSynchronizer</code>
- [L57](../fsgs/ogd/base.py#L57) — **FIXME** — <code># FIXME: change second {0} to {1}</code>
- [L82](../fsgs/ogd/base.py#L82) — **FIXME** — <code># FIXME: change second {0} to {1}</code>

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

### `fsgs/saves.py`

- [L11](../fsgs/saves.py#L11) — **TODO** — <code>TODO: Snapshots support. Create a Snapshots/TimeTDate/ directory with a</code>
- [L27](../fsgs/saves.py#L27) — **FIXME** — <code># FIXME: SaveHandler(fsgc, options=options) is new usage?</code>
- [L127](../fsgs/saves.py#L127) — **FIXME** — <code># FIXME: Correct?</code>
- [L167](../fsgs/saves.py#L167) — **FIXME** — <code># FIXME: Remove UUID/XX dir if empty?</code>

### `fsgs/util/archiveutil.py`

- [L60](../fsgs/util/archiveutil.py#L60) — **FIXME** — <code># FIXME: Create a uaem metadata helper class</code>

### `fsgs/util/gamenameutil.py`

- [L41](../fsgs/util/gamenameutil.py#L41) — **FIXME** — <code># FIXME: regular expression instead</code>
- [L236](../fsgs/util/gamenameutil.py#L236) — **FIXME** — <code># FIXME: Mark as deprecated</code>
- [L248](../fsgs/util/gamenameutil.py#L248) — **FIXME** — <code># FIXME: no longer allowed to send in paths!</code>

### `fspy/zipfile.py`

- [L66](../fspy/zipfile.py#L66) — **FIXME** — <code># FIXME: Remove non-needed empty directories</code>
- [L85](../fspy/zipfile.py#L85) — **FIXME** — <code># FIXME: Check if this is correct?</code>

### `fsui/common/layout.py`

- [L90](../fsui/common/layout.py#L90) — **FIXME** — <code># FIXME: Rename margin -&gt; margins (+ alias), margin_top -&gt; top, etc</code>
- [L170](../fsui/common/layout.py#L170) — **FIXME** — <code># FIXME: avoid calling update after both set_position and set_size</code>

### `fsui/qt/Button.py`

- [L22](../fsui/qt/Button.py#L22) — **FIXME** — <code># FIXME: Remove</code>

### `fsui/qt/ComboBox.py`

- [L10](../fsui/qt/ComboBox.py#L10) — **FIXME** — <code>&quot;FIXME: ComboBox not respecting read_only&quot;</code>

### `fsui/qt/Icon.py`

- [L8](../fsui/qt/Icon.py#L8) — **FIXME** — <code>FIXME: Add support for icon search path, so, during startup, a list</code>

### `fsui/qt/ImageButton.py`

- [L28](../fsui/qt/ImageButton.py#L28) — **FIXME** — <code># FIXME: Remove</code>

### `fsui/qt/TextArea.py`

- [L18](../fsui/qt/TextArea.py#L18) — **FIXME** — <code>print(&quot;FIXME: not respecting font_family yet&quot;)</code>

### `fsui/qt/dialogwindow.py`

- [L8](../fsui/qt/dialogwindow.py#L8) — **FIXME** — <code># FIXME: Intercept escape key and make it close the dialog window</code>

### `fsui/qt/label.py`

- [L18](../fsui/qt/label.py#L18) — **FIXME** — <code># FIXME: make Label more plain, and rather make a InteractiveLabel</code>

### `fsui/qt/widget.py`

- [L205](../fsui/qt/widget.py#L205) — **FIXME** — <code># FIXME: using exec now</code>

### `fsui/qt/widget_mixin.py`

- [L202](../fsui/qt/widget_mixin.py#L202) — **FIXME** — <code># FIXME: using exec now</code>

### `fsui/qt/window.py`

- [L194](../fsui/qt/window.py#L194) — **FIXME** — <code># FIXME</code>
- [L261](../fsui/qt/window.py#L261) — **FIXME** — <code># FIXME: Is this used?</code>
- [L439](../fsui/qt/window.py#L439) — **FIXME** — <code>print(&quot;FIXME: Window.set_icon_from_path&quot;)</code>

### `fsui/qt/windowbase.py`

- [L71](../fsui/qt/windowbase.py#L71) — **FIXME** — <code>print(&quot;FIXME: Window.set_icon_from_path&quot;)</code>

### `launcher/apps/fs_uae_launcher.py`

- [L77](../launcher/apps/fs_uae_launcher.py#L77) — **TODO** — <code>TODO: Add more documentation</code>

### `launcher/cd_manager.py`

- [L46](../launcher/cd_manager.py#L46) — **FIXME** — <code>print(&quot;FIXME: not calculating CD checksum just yet&quot;)</code>

### `launcher/configuration_scanner.py`

- [L58](../launcher/configuration_scanner.py#L58) — **FIXME** — <code># FIXME: try splitting name into name, variant pair, and</code>

### `launcher/database_refresh.py`

- [L54](../launcher/database_refresh.py#L54) — **FIXME** — <code># FIXME: review what signals should be sent when a scan is performed</code>
- [L55](../launcher/database_refresh.py#L55) — **FIXME** — <code># FIXME: these should be removed soon</code>

### `launcher/devicemanager.py`

- [L314](../launcher/devicemanager.py#L314) — **FIXME** — <code># FIXME: How to handle?</code>
- [L380](../launcher/devicemanager.py#L380) — **FIXME** — <code># FIXME: Should be put in platform-specific code, here for now.</code>

### `launcher/filescanner.py`

- [L209](../launcher/filescanner.py#L209) — **FIXME** — <code># FIXME: NES header hack. Would be better to add a proper notion of</code>
- [L211](../launcher/filescanner.py#L211) — **FIXME** — <code># FIXME: This will confuse some functionality, such as the</code>
- [L222](../launcher/filescanner.py#L222) — **FIXME** — <code># FIXME: Check if 128 is a fixed or variable number of bytes</code>
- [L317](../launcher/filescanner.py#L317) — **FIXME** — <code># FIXME: Enable use of filter mechanism for Cloanto ROMs</code>
- [L329](../launcher/filescanner.py#L329) — **FIXME** — <code># FIXME: size is incorrect here -- it&#x27;s the size of the parent</code>

### `launcher/floppy_manager.py`

- [L55](../launcher/floppy_manager.py#L55) — **FIXME** — <code># FIXME: get list of floppy extensions from a central</code>

### `launcher/gamescanner.py`

- [L226](../launcher/gamescanner.py#L226) — **FIXME** — <code># FIXME: log error</code>
- [L340](../launcher/gamescanner.py#L340) — **FIXME** — <code># FIXME: handle the/a (etc)</code>
- [L545](../launcher/gamescanner.py#L545) — **FIXME** — <code># FIXME: Remove this line?</code>

### `launcher/launcher_config.py`

- [L68](../launcher/launcher_config.py#L68) — **FIXME** — <code>(&quot;__version&quot;, &quot;FIXME&quot;),</code>
- [L577](../launcher/launcher_config.py#L577) — **FIXME** — <code># FIXME: errors should be logged / displayed</code>
- [L588](../launcher/launcher_config.py#L588) — **FIXME** — <code># FIXME: errors should be logged / displayed</code>
- [L839](../launcher/launcher_config.py#L839) — **FIXME** — <code># FIXME: parent</code>
- [L930](../launcher/launcher_config.py#L930) — **FIXME** — <code># FIXME: Set changed!</code>

### `launcher/launcherapp.py`

- [L121](../launcher/launcherapp.py#L121) — **FIXME** — <code># FIXME: should now sanitize check some options -for instance,</code>
- [L147](../launcher/launcherapp.py#L147) — **FIXME** — <code># FIXME: replace argument &quot;parsing&quot; with use of argparse module</code>
- [L194](../launcher/launcherapp.py#L194) — **FIXME** — <code># FIXME: Could also do this for floppy file archives.</code>
- [L234](../launcher/launcherapp.py#L234) — **FIXME** — <code># FIXME: Generate a better config name for save dir?</code>
- [L247](../launcher/launcherapp.py#L247) — **FIXME** — <code># FIXME: Generate a better config name for save dir?</code>
- [L606](../launcher/launcherapp.py#L606) — **FIXME** — <code># FIXME: Files to clean up:</code>

### `launcher/netplay/connection_tester.py`

- [L92](../launcher/netplay/connection_tester.py#L92) — **FIXME** — <code># FIXME: handle problem...</code>

### `launcher/option.py`

- [L1443](../launcher/option.py#L1443) — **FIXME** — <code>&quot;description&quot;: &quot;FIXME&quot;,</code>
- [L1459](../launcher/option.py#L1459) — **FIXME** — <code>&quot;description&quot;: &quot;FIXME&quot;,</code>

### `launcher/scanner.py`

- [L43](../launcher/scanner.py#L43) — **FIXME** — <code># FIXME: these should be removed soon</code>

### `launcher/settings/advanced_settings_page.py`

- [L51](../launcher/settings/advanced_settings_page.py#L51) — **FIXME** — <code># FIXME: accessing values directly here, not very nice</code>
- [L69](../launcher/settings/advanced_settings_page.py#L69) — **FIXME** — <code># FIXME: accessing values directly here, not very nice</code>

### `launcher/settings/language_settings_page.py`

- [L47](../launcher/settings/language_settings_page.py#L47) — **FIXME** — <code># FIXME: include in () what language is currently the automatic one</code>

### `launcher/settings/video_settings_page.py`

- [L38](../launcher/settings/video_settings_page.py#L38) — **FIXME** — <code># FIXME: Move 640 to constants</code>

### `launcher/setup/wizardheader.py`

- [L8](../launcher/setup/wizardheader.py#L8) — **FIXME** — <code># FIXME: From Theme</code>

### `launcher/ui/ConfigurationsBrowser.py`

- [L351](../launcher/ui/ConfigurationsBrowser.py#L351) — **FIXME** — <code># FIXME: lower-case search string?</code>

### `launcher/ui/ConfigurationsPanel.py`

- [L195](../launcher/ui/ConfigurationsPanel.py#L195) — **FIXME** — <code># FIXME: Do asynchronously, add to queue</code>

### `launcher/ui/LauncherFilePicker.py`

- [L53](../launcher/ui/LauncherFilePicker.py#L53) — **FIXME** — <code># FIXME: Return new Media directory instead</code>

### `launcher/ui/TabButton.py`

- [L67](../launcher/ui/TabButton.py#L67) — **FIXME** — <code># FIXME: check if mouse is hovering, used for example after having</code>

### `launcher/ui/VariantsBrowser.py`

- [L128](../launcher/ui/VariantsBrowser.py#L128) — **FIXME** — <code># FIXME: Merge code with</code>
- [L186](../launcher/ui/VariantsBrowser.py#L186) — **FIXME** — <code># FIXME: Add warning here that the favorite variant</code>

### `launcher/ui/behaviors/__init__.py`

- [L18](../launcher/ui/behaviors/__init__.py#L18) — **FIXME** — <code># FIXME: We need to disconnect the listener</code>

### `launcher/ui/behaviors/platformbehavior.py`

- [L17](../launcher/ui/behaviors/platformbehavior.py#L17) — **FIXME** — <code># FIXME: We need to disconnect the listener</code>
- [L64](../launcher/ui/behaviors/platformbehavior.py#L64) — **FIXME** — <code># FIXME: Temporarily disabled due to having to handle layout</code>

### `launcher/ui/config/CustomOptionsPage.py`

- [L78](../launcher/ui/config/CustomOptionsPage.py#L78) — **FIXME** — <code># FIXME: Move to LauncherConfig as a method, maybe use</code>

### `launcher/ui/config/HardDriveGroup.py`

- [L107](../launcher/ui/config/HardDriveGroup.py#L107) — **FIXME** — <code># FIXME: use contract function</code>

### `launcher/ui/config/InputSelector.py`

- [L199](../launcher/ui/config/InputSelector.py#L199) — **FIXME** — <code>print(&quot;FIXME: could not set mode&quot;)</code>

### `launcher/ui/config/expand.py`

- [L132](../launcher/ui/config/expand.py#L132) — **FIXME** — <code># FIXME: did it usually have 1 MB?</code>
- [L215](../launcher/ui/config/expand.py#L215) — **FIXME** — <code># FIXME: uae_dongle_type</code>
- [L336](../launcher/ui/config/expand.py#L336) — **FIXME** — <code># FIXME: Check valid values</code>
- [L344](../launcher/ui/config/expand.py#L344) — **FIXME** — <code># FIXME: check supported</code>
- [L907](../launcher/ui/config/expand.py#L907) — **FIXME** — <code># FIXME: chipmem size &gt; 2 MB</code>
- [L908](../launcher/ui/config/expand.py#L908) — **FIXME** — <code># FIXME:</code>
- [L967](../launcher/ui/config/expand.py#L967) — **FIXME** — <code># FIXME: depends on actual device in joystick_port_0...</code>
- [L979](../launcher/ui/config/expand.py#L979) — **FIXME** — <code># FIXME: depends on actual device in joystick_port_1...</code>
- [L989](../launcher/ui/config/expand.py#L989) — **FIXME** — <code># FIXME: depends on actual device in joystick_port_2...?</code>
- [L999](../launcher/ui/config/expand.py#L999) — **FIXME** — <code># FIXME: depends on actual device in joystick_port_3...?</code>
- [L1029](../launcher/ui/config/expand.py#L1029) — **FIXME** — <code># FIXME: should PPC / OS4 models be excluded?</code>
- [L1039](../launcher/ui/config/expand.py#L1039) — **FIXME** — <code># FIXME: check supported</code>
- [L1070](../launcher/ui/config/expand.py#L1070) — **FIXME** — <code># FIXME: check supported</code>
- [L1085](../launcher/ui/config/expand.py#L1085) — **FIXME** — <code># FIXME: ok? keep already specified value</code>
- [L1087](../launcher/ui/config/expand.py#L1087) — **FIXME** — <code># FIXME: check value</code>
- [L1115](../launcher/ui/config/expand.py#L1115) — **FIXME** — <code># FIXME: normalize to &quot;true&quot; or &quot;false&quot;</code>
- [L1126](../launcher/ui/config/expand.py#L1126) — **FIXME** — <code># FIXME: boolean</code>
- [L1138](../launcher/ui/config/expand.py#L1138) — **FIXME** — <code># FIXME: boolean</code>
- [L1532](../launcher/ui/config/expand.py#L1532) — **FIXME** — <code># FIXME: cards are missing here</code>
- [L1619](../launcher/ui/config/expand.py#L1619) — **FIXME** — <code># FIXME: Blizzard expansions!</code>
- [L1686](../launcher/ui/config/expand.py#L1686) — **FIXME** — <code># FIXME: ok? keep already specified value</code>
- [L1688](../launcher/ui/config/expand.py#L1688) — **FIXME** — <code># FIXME: match and normalize uae boolean</code>
- [L1697](../launcher/ui/config/expand.py#L1697) — **FIXME** — <code># FIXME: ok? keep already specified value</code>
- [L1699](../launcher/ui/config/expand.py#L1699) — **FIXME** — <code># FIXME: check value</code>
- [L1746](../launcher/ui/config/expand.py#L1746) — **FIXME** — <code># FIXME: check boolean</code>

### `launcher/ui/config/modelgroup.py`

- [L27](../launcher/ui/config/modelgroup.py#L27) — **FIXME** — <code># FIXME: remove with_more_button=True</code>

### `launcher/ui/download.py`

- [L168](../launcher/ui/download.py#L168) — **FIXME** — <code># FIXME: review what signals should be sent when a scan is performed</code>
- [L169](../launcher/ui/download.py#L169) — **FIXME** — <code># FIXME: these should be removed soon</code>

### `launcher/ui/floppiesgroup.py`

- [L61](../launcher/ui/floppiesgroup.py#L61) — **FIXME** — <code># FIXME: Drive count option does not work on the main page when</code>

### `launcher/ui/launcherwindow.py`

- [L224](../launcher/ui/launcherwindow.py#L224) — **FIXME** — <code># FIXME: Is this being run?</code>
- [L252](../launcher/ui/launcherwindow.py#L252) — **FIXME** — <code># FIXME: should check data directories (XDG_DATA_DIRS) properly</code>
- [L255](../launcher/ui/launcherwindow.py#L255) — **FIXME** — <code># FIXME: this encoding / decoding is a bit ridiculous, but, this is</code>
- [L265](../launcher/ui/launcherwindow.py#L265) — **FIXME** — <code># FIXME: Check relative to executable instead</code>

### `launcher/ui/options.py`

- [L264](../launcher/ui/options.py#L264) — **FIXME** — <code># FIXME: This can be removed if/when implicit value always</code>
- [L360](../launcher/ui/options.py#L360) — **FIXME** — <code># FIXME: Check range?</code>
- [L368](../launcher/ui/options.py#L368) — **FIXME** — <code># FIXME: This can be removed if/when implicit value always</code>

### `launcher/ui/pageddialog.py`

- [L56](../launcher/ui/pageddialog.py#L56) — **FIXME** — <code># FIXME: Problems with page height</code>

### `launcher/ui/savebutton.py`

- [L43](../launcher/ui/savebutton.py#L43) — **FIXME** — <code># FIXME: notify user</code>

### `launcher/ui/skin.py`

- [L56](../launcher/ui/skin.py#L56) — **FIXME** — <code># FIXME: Rename to launcher_bg/background_color and document.</code>
- [L75](../launcher/ui/skin.py#L75) — **FIXME** — <code># FIXME: Should really just check for Windows XP here, or maybe</code>

### `launcher/ui/statusbar/WarningsElement.py`

- [L368](../launcher/ui/statusbar/WarningsElement.py#L368) — **FIXME** — <code># FIXME: move such warnings to config model code instead</code>
- [L393](../launcher/ui/statusbar/WarningsElement.py#L393) — **FIXME** — <code># FIXME: Remove direct Qt dependency</code>
- [L404](../launcher/ui/statusbar/WarningsElement.py#L404) — **FIXME** — <code># FIXME: Move code to settings dialog, so we can open the page with</code>
- [L440](../launcher/ui/statusbar/WarningsElement.py#L440) — **FIXME** — <code># FIXME: Move code to settings dialog, so we can open the page with</code>

### `launcher/update_manager.py`

- [L56](../launcher/update_manager.py#L56) — **FIXME** — <code># FIXME: Thread safety...</code>
- [L57](../launcher/update_manager.py#L57) — **FIXME** — <code># FIXME: Use above signal instead</code>

### `workspace/apps/locker_uploader.py`

- [L141](../workspace/apps/locker_uploader.py#L141) — **FIXME** — <code># FIXME: Use Archive.open to get support for filter functions</code>
- [L142](../workspace/apps/locker_uploader.py#L142) — **FIXME** — <code># FIXME: Also use stream api, do not buffer entire file</code>
- [L195](../workspace/apps/locker_uploader.py#L195) — **FIXME** — <code># FIXME: prefix</code>
