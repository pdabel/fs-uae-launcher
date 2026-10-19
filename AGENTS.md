# Agent Instructions

FS-UAE Launcher -- a PySide6 (Qt 6) desktop launcher for the FS-UAE Amiga emulator, plus `fsnp-server`, a standard-library-only Go netplay server that speaks FSNP v1 byte for byte with `fs-uae v3.1.66`. The launcher finds games, writes FS-UAE configs, runs the emulator, and coordinates netplay over IRC (chat) and the lobby HTTP API (game config).

## References

| Topic | Link |
| --- | --- |
| Netplay design, wire protocol, rollout status | [docs/netplay-go-server-design.md](docs/netplay-go-server-design.md) |
| fsnp-server usage, flags, lobby API | [fsnp-server/README.md](fsnp-server/README.md) |
| Captured-session fixtures | [docs/netplay-fixtures/README.md](docs/netplay-fixtures/README.md) |
| Python/dependency TODO | [docs/python-dependency-modernization.md](docs/python-dependency-modernization.md) |
| Building and packaging | [docs/compiling.md](docs/compiling.md) |
| FS-UAE options | <https://fs-uae.net/docs/options/> |
| FSNP client (source of truth) | `fs-uae/libfsemu/src/emu/netplay.c` at tag `v3.1.66` (branch `fs-uae-3.1`) |
| Qt for Python | <https://doc.qt.io/qtforpython-6/> |

Use the codebase as the authoritative reference for patterns and style. Plan before implementing. Read files before modifying them.

---

## Build, Test, Validate

| Command | Purpose |
| --- | --- |
| `venv/bin/python -m pytest fsbc fstd fspy launcher/netplay` | The Python suite CI runs |
| `venv/bin/python -m pytest fsui/test/test_qt6.py` | Qt widget tests -- **not run by CI**; run them when UI or panel code changes |
| `make -C fsnp-server check` | gofmt check, `go vet`, `go test ./... -race` -- what CI runs |
| `make -C fsnp-server` | Build `fsnp-server/fsnp-server` where the launcher looks for it in dev mode |
| `venv/bin/python fs-uae-launcher` | Run the launcher from source |

Use `venv/bin/python -m pytest`, not `pipenv run pytest`: `pipenv run` can re-lock `Pipfile.lock` as a side effect. A Go install is optional; the Makefile falls back to a `golang` container.

---

## Project Layout

| Path | Purpose |
| --- | --- |
| `launcher/` | The launcher application: UI, panels, settings, config model, netplay client |
| `launcher/netplay/` | Netplay: IRC chat, lobby client, config apply/hash, the panel |
| `launcher/server/Server.py` | Spawns the bundled `fsnp-server` for `/hostgame` |
| `launcher/launcher_config.py` | Config model; `build_cfg()` tags keys `sync`/`checksum`; `checksum_config()` |
| `fsgs/` | Game-system layer: databases, file scanning, Amiga config writer, plugin/executable finder |
| `fsui/` | Widget toolkit over Qt (`fsui.qt` is the Qt import surface) |
| `fsbc/`, `fstd/`, `fspy/`, `fsboot/` | Base utilities: app/threading, logging, paths, signals, zip |
| `workspace/`, `amitools/`, `oyoyo/` | Workspace UI support, Amiga file tools, vendored IRC client |
| `fsnp-server/` | Go module: `cmd/fsnp-server`, `internal/fsnp` (codec), `internal/game`, `internal/lobby` |
| `fsbuild/` | Packaging scripts (PyInstaller, bundling, signing) used by CI |
| `.github/workflows/` | CI: `ci.yml` calls reusable `linux`, `macos`, `container`, `source`, `netplay-server` workflows |

---

## Skills

| Skill | SDLC Stage | When to load |
| --- | --- | --- |
| `fsl-planning` | Plan | Starting any non-trivial task, creating implementation plans, splitting work into commits |
| `fsl-structure` | Plan + Dev | Exploring the codebase, tracing launcher or netplay data flow, placing a change |
| `fsl-netplay` | Dev | Changing the FSNP protocol, the lobby API, config sync/hash, `Server.py`, or netplay UI |
| `fsl-testing` | Test | Writing pytest, Qt widget, Go, golden-fixture, or launcher-to-server contract tests |
| `fsl-debugging` | Bugfix | Diagnosing launcher crashes, netplay failures, desyncs, server spawn problems |
| `fsl-ci-packaging` | Dev + Review | Workflows, Dependabot, `fsbuild/`, PyInstaller bundles, the `fsnp-server` image |
| `fsl-code-review` | Review | Reviewing a PR, branch, or diff |

---

## Key Invariants

- **FSNP is pinned to `fs-uae v3.1.66`.** Hardcode its command numbering, not fs-uae master's (master renumbered without a protocol bump). Never send `READY`, `SET_PLAYER_TAG`, `PROTOCOL_VERSION`, `EMULATION_VERSION` or `HALT` to a v1 client -- it disconnects. Socket writes stay capped at 1,400 bytes (client bug C1). This repo does not modify fs-uae's C source.
- **Protocol quirks are tested, not "fixed".** Sender echo of input events, checksums attributed to the previous frame, the 3-byte session key, 100-word auto-flush, `PING`/`PONG` -- each has a golden test. Changing one is a protocol change.
- **One config hash, two implementations.** Python `LauncherConfig.checksum_config()` and Go `game.ConfigHash` must agree. `fsnp-server/internal/game/testdata/config-hash.json` is the only fixture and both suites read it. Change both sides and the fixture in the same commit.
- **Python owns the key vocabulary.** `build_cfg()` in `launcher/launcher_config.py` defines which keys are `sync`/`checksum`. The Go server treats keys as opaque strings handed to it; it must not grow an Amiga-config vocabulary.
- **Golden bytes live once.** `fsnp-server/internal/fsnp/testdata/` is the only copy of the captured-session fixtures. `docs/netplay-fixtures/` documents them; do not copy bytes there.
- **`fsnp-server` uses the Go standard library only.** No `require` lines in `go.mod`, no `go.sum`. Build flags (`CGO_ENABLED=0 -trimpath -ldflags="-s -w"`) are duplicated in `fsnp-server/Makefile`, `fsbuild/build.sh` and `fsnp-server/Dockerfile`; change all three together.
- **UI thread.** No blocking network or disk I/O on the Qt thread; do it on a worker thread and return results with `fsbc.application.call_after`. Every HTTP call has a timeout.
- **Qt binding.** PySide6 through `fsui.qt`/QtPy. Never import PyQt5 or mix bindings in one process.
- **Untrusted input.** IRC messages, lobby responses, and peers' config documents are untrusted. Netplay config is applied only through the sync-key allowlist; files arrive by SHA-1 and resolve through the local file database, never as paths.
- **Formatting.** `black` with line length 79 (`pyproject.toml`), `gofmt` for Go. Many legacy Python files are not black-clean: format the code you change, not whole files.
- **Commits.** Each commit is one reviewable step that passes both suites on its own; branches may be published as a stack of PRs. Branch from a remote ref with `--no-track`.
- **Design doc status.** `docs/netplay-go-server-design.md` keeps rollout status current. A change that completes or alters a rollout step updates it in the same commit.

---

## Code Review

For any review of a PR, branch, or diff, load and follow [`fsl-code-review`](.github/skills/fsl-code-review/SKILL.md). It owns the workflow, severities, completeness gate, and the "do not comment" list, and delegates codebase rules to the domain skills.

Minimum reviewer discipline:

- Comment only at >80% confidence, with a verified file and line.
- For protocol claims, cite the design doc section or `netplay.c` at `v3.1.66`; for FS-UAE option claims, cite <https://fs-uae.net/docs/options/>.
- Never post secrets, tokens, or passwords in review output.
