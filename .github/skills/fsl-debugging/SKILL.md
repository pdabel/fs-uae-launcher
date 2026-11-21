---
name: fsl-debugging
description: 'Debugging and troubleshooting for FS-UAE Launcher and fsnp-server. Use when diagnosing launcher crashes or hangs, Qt/theme problems, fsnp-server spawn or port failures, players rejected or dropped, netplay desyncs, config-hash mismatches, or failing tests.'
---

# Debugging and Troubleshooting

Start from logs, then reproduce in a test. A netplay bug that cannot be reproduced in a Go or pytest test should at least be pinned to a log line before changing code.

## Where to look

| What | Where |
| --- | --- |
| Launcher log | `<logs>/` from `FSGSDirectories.get_logs_dir()` -- `<base>/Cache/Logs` unless portable. `fsbc.logging` replaces `sys.stdout`/`stderr`, so prints land here |
| Local server log | `<logs>/fsnp-server.log.txt` (the launcher passes `--log-file`; path also printed as `Netplay server log:`) |
| Lobby server | `docker logs <container>`, or `LOG_FILE` in a volume writable by uid 101 |
| Server verbosity | `--verbose` for debug; `--log-input=false` to drop per-input lines |
| Run from source in a debugger | `.vscode/launch.json` -> "Python Debugger: FS-UAE-Launcher" (`PYTHONPATH` = repo root) |
| Emulator side | Run `fs-uae` from a terminal with the same `--netplay_*` options to see the C client's messages |

## Launcher

### Crash or exception at startup

1. Read the launcher log for the traceback.
2. Qt binding: PySide6 only. A traceback mentioning PyQt5, or two bindings imported, means something bypassed `fsui.qt`. Check `QT_API` (set to `pyside6` by `configure_qt_environment`).
3. Theme: try `--launcher-theme=fusion-plain` to separate theme code from the rest. Unknown saved themes fall back to Fusion; an empty setting means Modern Dark.

### UI freezes

Almost always blocking I/O on the Qt thread: an HTTP call (lobby, `/startgame`), a socket connect, or a file scan. Find the call from the stack (`py-spy dump --pid <pid>` if installed), move it to a worker thread, return through `fsbc.application.call_after`, and give it a timeout.

### Setting doesn't reach the emulator

Trace `LauncherConfig.set` -> the start path in `launcher/launcherapp.py` -> the FS-UAE config written by `fsgs/amiga/`. Check whether the key is renamed or filtered on the way (netplay `__netplay_*` keys are copied into `netplay_*` only when non-empty).

## Netplay

| Symptom | Likely cause | Check |
| --- | --- | --- |
| `/hostgame` fails at once | Port 25101 in use by another server or lobby | Server log line for the failed listen; `lsof -i :25101` |
| `/hostgame` hangs then errors | Binary not found, or it never printed the readiness line | Launcher log; `make -C fsnp-server` in dev mode; `PluginExecutableFinder` for packaged builds |
| Player gets `ERROR_WRONG_PASSWORD` in a no-password game | Stale `netplay_password` left in that player's config by an earlier game (only copied when non-empty) | That player's config; design-doc Risks |
| `no game for password` in lobby log | Player connected with a password no live game has: wrong game, or the game already ended | Lobby log `game created` / removal lines |
| `/game/create` 409 / 503 | Password collides with a live game / `--max-games` reached or shutting down | Lobby log |
| Config sync slow, op disconnected from IRC | IRC flood limits (one message per key) | Use `fsnp-server/irc/netplay.conf` limits; prefer lobby-held config |
| "not the same config hash" / player not ready | A sync key differs or a file is missing locally | Compare `checksum_config()` inputs; `missing` SHA-1s from `apply_config`; run `test_checksum_golden.py` |
| Desync (`mem`/`rnd` check error) mid-game | Emulator state diverged: different config not covered by the checksum keys, different kickstart/media, or a timing-sensitive option | Server log for the frame and check type; diff both players' FS-UAE configs |
| One player drops, others continue offline | Disconnect is terminal for the v1 client; the server tolerates stalls but not a dead socket | Server log for the player's last frame and `lag_ms` |
| Corrupted stream on large flushes | A write larger than 1,400 bytes (client bug C1) | Writer cap in `internal/game/conn.go` |

### Reproducing a session without the launcher

```sh
make -C fsnp-server
fsnp-server/fsnp-server --port=25100 --players=2 --password=test --verbose
fs-uae --netplay_server=127.0.0.1 --netplay_port=25100 --netplay_password=test --netplay_tag=P1 <game>
fs-uae --netplay_server=127.0.0.1 --netplay_port=25100 --netplay_password=test --netplay_tag=P2 <game>
```

Healthy sessions log steady `ping_ms`/`lag_ms` and no desync. Lobby mode: `fsnp-server/fsnp-server --lobby`, then `curl 'http://127.0.0.1:25101/game/create?players=2'`.

## Tests

| Failure | Meaning |
| --- | --- |
| `test_checksum_golden.py` or `confighash_test.go` fails | Python and Go disagree on the hash, or the fixture is stale. Fix the implementation, not the fixture, unless the hash change is intended -- then regenerate and run both |
| Contract tests skipped | No `fsnp-server` binary and no `go`. Set `FSNP_SERVER` or install Go; a skip is not a pass |
| Contract test fails but unit tests pass | The client's assumptions about the API differ from the server. Trust the server test suite, then fix whichever side diverged from the README API |
| Go test fails only with `-race` | Shared state touched from two goroutines; give it one owner or a mutex. Never drop `-race` to pass |
| Go test flaky on timing | Real clock used where the fake `Clock` should be |
| Qt test fails headless | Set `QT_QPA_PLATFORM=offscreen` |
| A test passes alone, fails in the suite | Leaked global state: `LauncherConfig`, `fsui.theme`/`theme_variant`, environment variables. Restore with `monkeypatch`/`patch` |

## Fix discipline

- Find the layer that produced the bad value and fix it there (see `fsl-structure`), not where it surfaced.
- Add a test that fails before the fix: a pytest case, a Go table row, or a golden case.
- For protocol-level fixes, confirm the behaviour against `netplay.c` at `v3.1.66` before changing the server.
