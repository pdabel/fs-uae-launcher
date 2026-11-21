---
name: fsl-planning
description: 'Task planning and approach strategy for FS-UAE Launcher. Use when starting any non-trivial task, reading an issue or the netplay design doc, planning before implementing, or splitting a change into stackable commits.'
---

# Planning and Task Approach

## Before Writing Code

1. **Read the requirement.** Check the linked issue or PR. For netplay work, read the relevant section of `docs/netplay-go-server-design.md` (server, protocol, session API) or `docs/netplay-rooms-design.md` (lobby browser, hosting, joining) first -- they record decisions and measured behaviour that are not visible in the code. For moving code between packages, read `docs/architecture.md`.
2. **Write acceptance criteria.** State what "done" looks like in testable terms: what should work, what should be rejected, and what must not break (existing `v3.1.66` clients, saved configs, other themes).
3. **Identify trust boundaries.** Does this change:
   - Accept data from the lobby API (listings, names, titles) or another player's launcher? -> validate at the boundary, allowlist keys, never treat values as paths, commands or markup.
   - Change what goes on the FSNP wire? -> it is a protocol change; see `fsl-netplay`.
   - Touch the host token, game password, or anything else a peer must not learn? -> keep it out of logs, the activity log, and UI.
   - Change what a lobby lists or what browsing sends? -> check the privacy model in the rooms design's "Security".
4. **Identify affected layers** (see `fsl-structure`):
   - UI (`launcher/ui/`, `launcher/panels/`, `launcher/settings/`, `fsui/`)
   - Config model (`launcher/launcher_config.py`, `fsgs/amiga/`)
   - Netplay client (`launcher/netplay/`, `launcher/server/Server.py`)
   - Netplay server (`fsnp-server/`)
   - Packaging and CI (`fsbuild/`, `.github/workflows/`, `fsnp-server/Dockerfile`)
5. **Check the Key Invariants in `AGENTS.md`**, especially the `v3.1.66` pin, the shared config-hash fixture, and the UI-thread rule.
6. **Identify the test surface** (see `fsl-testing`): pytest units, Qt widget tests, Go tests, golden fixtures, the Python-to-Go contract tests.
7. **Produce a plan.** Files to change, in order, and the commit boundaries. Include what must not break.

## Layer Impact Checklist

- [ ] Changes a `sync` or `checksum` key in `build_cfg()`? -> regenerate or extend `fsnp-server/internal/game/testdata/config-hash.json`; both suites must pass.
- [ ] Changes the hash algorithm or key order? -> change `checksum_config()` and `game.ConfigHash` together, plus the fixture.
- [ ] Changes a lobby endpoint or JSON field? -> Go handler, `launcher/netplay/lobby_client.py` (or `lobby_browser.py` for the listing), the contract test, `fsnp-server/README.md` API section. New fields default to the old behaviour, since lobbies and launchers update separately.
- [ ] Changes FSNP bytes on the wire? -> stop and confirm against `netplay.c` at `v3.1.66`; add a golden test.
- [ ] Adds a `fsnp-server` flag? -> flag, env var, README table, and `Server.py` if the launcher passes it.
- [ ] Touches a panel or settings page? -> works in every launcher theme (`LAUNCHER_THEME` in `launcher/option.py`); run `fsui/test`.
- [ ] Adds user-visible text? -> through `gettext` from `launcher.i18n` (`fsui.res` or `fsgs.res` below the launcher).
- [ ] Adds network or disk I/O reachable from the UI? -> worker thread + `call_after`, with a timeout.
- [ ] Adds a Python dependency? -> `Pipfile` and `Pipfile.lock`, and check PyInstaller still bundles it.
- [ ] Adds a Go dependency? -> don't; the module is standard-library only.
- [ ] Completes or changes a netplay rollout step? -> update the design doc status.

## Definition of Done

| Condition | Required action | Verification |
| --- | --- | --- |
| Any Python change | Python suite and lint pass | `venv/bin/python -m pytest fsbc fstd fspy fsgs/tests fsbuild/tests launcher/netplay launcher/server/tests launcher/tests`; `ruff check` |
| UI, panel, theme, or `fsui` change | Qt tests pass | `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest fsui/test` |
| Any `fsnp-server` change | Go checks pass | `make -C fsnp-server check` |
| Config-hash change | Both suites read the regenerated fixture | Python `test_checksum_golden.py` and Go `confighash_test.go` pass |
| Lobby API change | Contract test runs, not skips | `pytest -rs launcher/netplay` shows no skip for missing `fsnp-server` |
| New launcher behaviour you can only see in the app | Run it | `venv/bin/python fs-uae-launcher`, exercise the path |
| Multi-commit branch | Every commit is green | Run both suites at each commit in a scratch worktree |

## Scope Assessment

| Scope | Indicators | Action |
| --- | --- | --- |
| Trivial | Typo, docs, comment | Fix directly |
| Small | One layer, <50 lines, no protocol or API change | Brief plan -> implement -> test |
| Medium | Two layers, or a lobby API change | Plan with commit boundaries -> implement layer by layer |
| Large | Protocol change, new netplay phase, cross-cutting UI rework | Update the design doc first, get agreement, then land as a stack of commits |

## Commit Strategy

Branches here are often published as a stack of PRs, one per commit.

- Each commit is one reviewable step and passes both suites on its own.
- Server before client: land a Go endpoint (with its tests) before the Python code that calls it, so every commit in between still works.
- A test broken by an earlier unpushed commit is fixed by amending that commit, not by a later "fix tests" commit.
- Branch from a remote ref with `git switch -c <name> --no-track origin/main`, then `git push -u origin <name>`.

## Ordering for Netplay Changes

1. Design doc -- if the change alters the contract or a rollout step.
2. Go server -- codec, game, or lobby code with tests and fixtures.
3. Shared fixtures -- `config-hash.json` or FSNP `testdata/`.
4. Python client -- `lobby_client.py`, `lobby_browser.py`, `session.py`, `config_apply.py`, `netplay.py`, `Server.py`.
5. Contract test -- Python client against a real `fsnp-server`.
6. UI -- `lobby_browser_panel.py`, the Net Play settings page; Qt tests.
7. Docs -- `fsnp-server/README.md` and the matching design doc's status line.

## Common Planning Mistakes

- Assuming fs-uae master's FSNP command numbers -- the client in use is `v3.1.66`.
- "Fixing" a protocol quirk that the C client depends on.
- Changing `build_cfg()` keys without touching the shared hash fixture.
- Teaching the Go server about Amiga config keys instead of taking the key list from the launcher.
- Blocking the Qt thread on an HTTP call, or making one with no timeout.
- Testing only the default Modern Dark theme.
- Adding a lobby request field whose absence doesn't mean the old behaviour, so an older lobby or launcher misreads it.
- Running `pipenv run` and committing an accidental `Pipfile.lock` re-lock.
- Reformatting a whole legacy file with black inside a behaviour change.
