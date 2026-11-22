---
name: fsl-testing
description: 'Testing patterns for FS-UAE Launcher: pytest suites, Qt widget tests, fsnp-server Go tests with the race detector, golden fixtures shared between Go and Python, and contract tests that run the Python lobby client against a real fsnp-server. Use when writing or running tests, adding fixtures, or checking that a branch is green commit by commit.'
---

# FS-UAE Launcher Testing

## Commands

| Command | Covers | In CI? |
| --- | --- | --- |
| `venv/bin/python -m pytest fsbc fstd fspy fsgs/tests fsbuild/tests launcher/netplay launcher/server/tests launcher/tests` | Base utilities, game system, packaging helpers, netplay client, golden hash, contract tests, server spawning, launcher behaviour | Yes (`linux-test.yml`, `macos-test.yml`) |
| `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest fsui/test` | Qt 6 environment, widgets, panels, themes, the Net Play tab | Yes (same workflows) |
| `black --check .` | Formatting | Yes (`ci.yml`, before the tests) |
| `ruff check` | Pyflakes and pycodestyle errors, string formatting (rules in `pyproject.toml`) | Yes (`ci.yml`, before the tests) |
| `make -C fsnp-server check` | `gofmt -l`, `go vet`, `go test ./... -race -count=1` | Yes (`netplay-server.yml`) |
| `make -C fsnp-server build` | The binary builds | Yes |
| `venv/bin/python -m pytest -rs launcher/netplay` | The netplay tests, listing skip reasons | -- |

CI runs both Python commands through `pipenv run`, on Linux and macOS, with Python 3.12 and 3.15, and `QT_QPA_PLATFORM=offscreen`. Both runners have Go, so the contract tests build `fsnp-server` and run there. Locally use `venv/bin/python -m pytest`, not `pipenv run pytest` (it can re-lock `Pipfile.lock`). Go is optional: the Makefile runs in a `golang` container without it; `GO_DOCKER=1` forces that.

---

## Where tests live

| Area | Location | Style |
| --- | --- | --- |
| Base utilities | `fsbc/tests/`, `fspy/tests/` | pytest / unittest |
| Game system, packaging helpers | `fsgs/tests/`, `fsbuild/tests/` | pytest |
| Launcher behaviour | `launcher/tests/` (configs, displays, portable mode, CPU performance) | pytest |
| Server spawning, executable lookup | `launcher/server/tests/test_server_start.py` | pytest, `tmp_path` stand-ins, `Mock` processes |
| Netplay client | `launcher/netplay/tests/`: `test_config_apply.py`, `test_apply_document.py`, `test_checksum_golden.py`, `test_lobby_client.py`, `test_session.py`, `test_lobby_browser.py`, `test_lobby_servers.py`, `test_netplay_flow.py` | pytest, `monkeypatch`, fake HTTP sessions, synchronous `dispatch` |
| Contract tests | `launcher/netplay/tests/test_lobby_contract.py`, `test_server_lobby.py` | pytest against a real `fsnp-server --lobby` |
| Qt widgets, themes, launch UI, Net Play tab | `fsui/test/` (`WidgetTestCase`, `test_qt6.py`, `test_button.py`, `test_text_field.py`) | unittest under pytest; needs a display, or `QT_QPA_PLATFORM=offscreen` on a headless machine |
| FSNP codec | `fsnp-server/internal/fsnp/*_test.go` | Golden tests against `testdata/` |
| Game | `fsnp-server/internal/game/*_test.go` | `net.Pipe()` clients, fake `Clock`, replays the captured session |
| Lobby | `fsnp-server/internal/lobby/*_test.go` | Loopback TCP |
| CLI | `fsnp-server/cmd/fsnp-server/main_test.go` | `run()` with injected args and stdio |

---

## Golden fixtures shared across languages

| Fixture | Read by | Proves |
| --- | --- | --- |
| `fsnp-server/internal/game/testdata/config-hash.json` | `confighash_test.go`, `launcher/netplay/tests/test_checksum_golden.py` | Launchers and server agree when configs match |
| `fsnp-server/internal/fsnp/testdata/*.bin`, `manifest.json` | `internal/fsnp` and `internal/game` tests | Byte compatibility with `fs-uae v3.1.66` |

Rules:

- One copy only. Python tests reach into `fsnp-server/.../testdata/` by relative path.
- Adding a case: add it to the JSON, run **both** suites. A case that passes in one language only is a real bug.
- The Python golden test monkeypatches `LauncherConfig.checksum_keys` with the case's own key list, because the live list depends on the machine's settings. Do the same in new tests rather than depending on global state.
- Never hand-edit `.bin` captures.

---

## Contract tests (Python client vs real server)

Tests that run `LobbyClient` against a real `fsnp-server --lobby` use the `fsnp_server_binary` fixture in `launcher/netplay/tests/conftest.py`:

1. `FSNP_SERVER=<path>` if set;
2. else a fresh `go build` into a temp dir when `go` is on `PATH` (a stale `make` binary may predate the API under test);
3. else `fsnp-server/fsnp-server` if present;
4. else skip.

On top of it, `lobby_port` is one session-wide lobby on `127.0.0.1` (port 0, read from the readiness line), and `presence_lobby_port` is a fresh named `--presence` lobby per test. Use `run_lobby(binary, *flags)` for another flag combination rather than spawning the server by hand.

A skip is not a pass. After an API change, run with `-rs` and confirm the contract tests ran. Unit tests pin what the client sends; the contract test pins that the server agrees.

---

## Patterns

- **Netplay client:** inject dependencies (`find_by_sha1`, setters, HTTP session) rather than patching module globals; `config_apply.resolve_config` is the model. `NetplaySession` and `LobbyBrowser` take `dispatch`, `later` and `on_change` for the same reason.
- **Threads:** code that posts back with `call_after` -- pass a synchronous `dispatch`, patch `call_after` to call synchronously, or drive the fake's event loop; don't sleep.
- **Host and player configs differ:** a flow test where host and players share one `LauncherConfig` can't catch a player applying the wrong thing. Test apply against a config that differs from the host's.
- **Data folder:** the root `conftest.py` sets `FS_UAE_BASE_DIR` to a temp dir for the whole run, so no suite reads or writes the user's `~/FS-UAE` (`Settings.ini` is saved at exit). A test of behaviour without that override removes it, as `test_portable.py` and the portable-mode test in `test_qt6.py` do.
- **Deprecations:** `pyproject.toml`'s pytest `filterwarnings` turns a `DeprecationWarning` raised in our own packages into a test failure; third-party ones stay warnings. Stop calling a deprecated helper rather than silencing it.
- **Go:** table-driven tests; a fake clock instead of `time.Sleep`; `-race` is always on, so shared state needs a mutex or a single owning goroutine.
- **Negative tests:** every allowlist, password, token, or status-code path gets a rejection test (unknown key, wrong token, full game, duplicate password -> 409).
- **Qt:** cover every theme a change affects (the `LAUNCHER_THEME` values in `launcher/option.py`). `test_qt6.py` loops variants with `subTest` and `patch.object(fsui, "theme_variant", variant)` -- extend that rather than adding a new harness, and restore `fsui.theme`/`fsui.theme_variant` afterwards as the existing tests do.
- **Qt widget lifetime:** end a dialog test with `run_dialog()`, which deletes the dialog through Qt (`deleteLater` and a `DeferredDelete` flush). A widget tree left to Python's garbage collector is freed at an arbitrary point in a later test and can crash a later application-wide `setStyleSheet()` -- on CI's macOS Python 3.12 job it did. Delete other top-level widgets a test creates the same way.

---

## Self-check before declaring done

- [ ] `black --check .`, `ruff check` and the Python suite pass.
- [ ] `fsui/test` passes if any UI, theme, panel, or `fsui` code changed. CI runs it, but run it locally before pushing.
- [ ] `make -C fsnp-server check` passes if anything under `fsnp-server/` changed.
- [ ] Contract tests ran (not skipped) if the lobby API changed.
- [ ] A changed hash or key list is reflected in `config-hash.json` and both suites pass.
- [ ] On a multi-commit branch, every commit passes on its own (scratch `git worktree add --detach`, run both suites at each commit, remove the worktree).
