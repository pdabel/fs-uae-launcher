---
name: fsl-testing
description: 'Testing patterns for FS-UAE Launcher: pytest suites, Qt widget tests, fsnp-server Go tests with the race detector, golden fixtures shared between Go and Python, and contract tests that run the Python lobby client against a real fsnp-server. Use when writing or running tests, adding fixtures, or checking that a branch is green commit by commit.'
---

# FS-UAE Launcher Testing

## Commands

| Command | Covers | In CI? |
| --- | --- | --- |
| `venv/bin/python -m pytest fsbc fstd fspy launcher/netplay` | Base utilities, netplay client, golden hash, contract tests | Yes (`linux.yml`, `macos.yml`, via `pipenv run`) |
| `venv/bin/python -m pytest fsui/test/test_qt6.py` | Qt 6 environment, widgets, panels, themes | **No** |
| `make -C fsnp-server check` | `gofmt -l`, `go vet`, `go test ./... -race -count=1` | Yes (`netplay-server.yml`) |
| `make -C fsnp-server build` | The binary builds | Yes |
| `venv/bin/python -m pytest -rs launcher/netplay` | Same as above, listing skip reasons | -- |

Locally use `venv/bin/python -m pytest`, not `pipenv run pytest` (it can re-lock `Pipfile.lock`). Go is optional: the Makefile runs in a `golang` container without it; `GO_DOCKER=1` forces that.

---

## Where tests live

| Area | Location | Style |
| --- | --- | --- |
| Base utilities | `fsbc/tests/`, `fspy/tests/` | pytest / unittest |
| Netplay client | `launcher/netplay/tests/` | pytest, `monkeypatch`, fakes over real sockets |
| Qt widgets, themes, launch/netplay UI | `fsui/test/` (`WidgetTestCase`, `test_qt6.py`) | unittest under pytest; needs a display, or `QT_QPA_PLATFORM=offscreen` on a headless machine |
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

A skip is not a pass. After an API change, run with `-rs` and confirm the contract tests ran. Unit tests pin what the client sends; the contract test pins that the server agrees.

---

## Patterns

- **Netplay client:** inject dependencies (`find_by_sha1`, setters, HTTP session) rather than patching module globals; `config_apply.resolve_config` is the model.
- **Threads:** code that posts back with `call_after` -- patch `call_after` to call synchronously, or drive the fake's event loop; don't sleep.
- **Go:** table-driven tests; a fake clock instead of `time.Sleep`; `-race` is always on, so shared state needs a mutex or a single owning goroutine.
- **Negative tests:** every allowlist, password, token, or status-code path gets a rejection test (unknown key, wrong token, full game, duplicate password -> 409).
- **Qt:** cover every theme a change affects. `test_qt6.py` loops variants with `subTest` and `patch.object(fsui, "theme_variant", variant)` -- extend that rather than adding a new harness, and restore `fsui.theme`/`fsui.theme_variant` afterwards as the existing tests do.

---

## Self-check before declaring done

- [ ] Python suite passes.
- [ ] `fsui/test/test_qt6.py` passes if any UI, theme, panel, or `fsui` code changed.
- [ ] `make -C fsnp-server check` passes if anything under `fsnp-server/` changed.
- [ ] Contract tests ran (not skipped) if the lobby API changed.
- [ ] A changed hash or key list is reflected in `config-hash.json` and both suites pass.
- [ ] On a multi-commit branch, every commit passes on its own (scratch `git worktree add --detach`, run both suites at each commit, remove the worktree).
