---
name: fsl-netplay
description: 'Rules and completeness checklists for netplay changes in FS-UAE Launcher: the FSNP v1 wire protocol, fsnp-server games and lobby, the lobby HTTP/session API, config sync and the shared config hash, Server.py spawning, and the netplay panel. Use when adding or changing anything that crosses the launcher-to-server or server-to-emulator boundary.'
---

# Netplay Changes

Netplay has three parties and two contracts:

```text
launcher (Python)  --lobby HTTP / JSON-->  fsnp-server (Go)  <--FSNP v1 bytes--  fs-uae v3.1.66 (C)
       \_____________________ IRC (chat, finding each other) ____________________/
```

The **FSNP contract is fixed** by a C client this repo does not change. The **launcher-to-server contract is ours**, and both ends live in this repo, so both must change in the same commit or in server-first order.

`docs/netplay-go-server-design.md` is the spec. Read the section for the area you touch before editing; it records measured behaviour and decisions that are not obvious from the code.

---

## FSNP v1 (server <-> emulator)

The client is `fs-uae/libfsemu/src/emu/netplay.c` at tag `v3.1.66`. It is the source of truth; when the design doc and the client disagree, the client wins and the doc gets fixed.

| Rule | Why |
| --- | --- |
| Use `v3.1.66` command numbering in `internal/fsnp` | fs-uae master renumbered extended messages without bumping the protocol version; a master-numbered server breaks the clients in use |
| Never send `READY`, `SET_PLAYER_TAG`, `PROTOCOL_VERSION`, `EMULATION_VERSION`, `HALT` | Defined on both sides, but the v1 client drops the connection on receipt |
| Cap each socket write at 1,400 bytes | Client bug C1: a partial read in `receive_thread` corrupts the stream on large flushes |
| Keep: sender echo of inputs, checksums attributed to the previous frame, 3-byte session key, 100-word auto-flush, `PLAYER_TAG_0 + i`, `PING`/`PONG`, 16-bit text length | The client depends on each; each is a golden test |
| Server pauses are safe; disconnect is terminal | The client waits indefinitely for the next frame word, but cannot rejoin |
| Error words go ahead of queued data | `sendError` ordering; the client must see the error before the stream ends |

Changing any of these is a protocol change: it needs a golden test that fails before and passes after, and a design-doc update. A change that needs the emulator to change is out of scope (see "Protocol v2 temptation" in the doc's Risks).

### Golden fixtures

- `fsnp-server/internal/fsnp/testdata/` holds the captured two-player session (`*-handshake.bin`, `*-to-server.bin`, `server-to-*.bin`, `manifest.json`). It is the only copy. `docs/netplay-fixtures/` documents it and holds the extractor script.
- `internal/game` tests replay the captured session through `net.Pipe()` clients with a fake clock.
- Never edit `.bin` files by hand. New fixture bytes come from a capture or from running the C client's own encoders.

---

## Launcher <-> server

### Single-game mode (`/hostgame`)

`launcher/server/Server.py` spawns the binary found by `PluginExecutableFinder` (`"fsnp-server": "FS-UAE-Netplay-Server"`) with `--exit-on-stdin-close` and `--log-file`, then blocks on a helper thread for the stdout readiness line `{"event":"listening","port":N}`. It reads only `event` and `port`; new fields are additive. `Server.stop()` closes stdin; `kill()` after `STOP_TIMEOUT` is the fallback.

| If you change... | Also change |
| --- | --- |
| A flag the launcher passes | `cmd/fsnp-server` flag + env var, `Server.py`, README flag table |
| The readiness line | Keep `event`/`port` stable; extend only |
| Default port | It is 25101 for both modes; the server's bind decides, not a launcher pre-check (a `SO_REUSEADDR`-less pre-check refused ports in `TIME_WAIT`) |

### Lobby mode (`--lobby`, port 25101)

One port: `internal/lobby/sniff.go` reads the first four bytes -- `FSNP` goes to the password-hash router, `PING` gets `PONG`, anything else is replayed into the HTTP server. Every lobby game has a unique password because the password routes the connection.

| If you change... | Also change |
| --- | --- |
| An endpoint, status code, or JSON field | Go handler + tests, `launcher/netplay/lobby_client.py` + unit tests, the contract test against a real server, README "API" section |
| Session state transitions | Go state machine tests, `launcher/netplay/session.py` and its tests, the panel that renders the state |
| Auth (host token, player token) | Never log tokens; keep them out of chat and UI; same commit on both sides |
| Timeouts (`--idle-timeout`, `--game-launch-timeout`, long-poll wait) | README table; the Python client's HTTP timeout must exceed the long-poll wait |

Order: server endpoint with tests first, then the client that calls it, so every commit in a stack works.

---

## Config sync and the hash

| Piece | Location |
| --- | --- |
| Which keys travel (`sync`) and which are hashed (`checksum`) | `build_cfg()` in `launcher/launcher_config.py` -- the only vocabulary |
| Hash | `LauncherConfig.checksum_config()` (Python), `game.ConfigHash` (Go) |
| Golden cases | `fsnp-server/internal/game/testdata/config-hash.json`, read by `confighash_test.go` and `launcher/netplay/tests/test_checksum_golden.py` |
| Applying a host's config | `launcher/netplay/config_apply.py`: allowlist against sync keys; kickstarts and media by SHA-1 through the local file database; returns what could not be found |

Rules:

- The Go server never hardcodes Amiga keys. It is handed `keys: {sync, checksum}` and treats keys and values as opaque strings.
- A change to the hash (algorithm, key order, empty-value handling) changes both implementations and the fixture in one commit. A Python-only or Go-only hash change is a desync waiting for a real session.
- Values from a peer are data. They are never used as file paths, commands, or format strings; files are looked up by SHA-1 only.
- An empty kickstart SHA-1 means "no kickstart", not "missing kickstart".

---

## IRC

After phase three IRC carries chat only. Don't add new protocol traffic to IRC; it is plaintext, flood-limited (a stock InspIRCd took ~40 s per 48-key sync), and the `__` command parser was the least robust code in the path. `fsnp-server/compose.yaml` + `irc/netplay.conf` is the reference IRC setup.

---

## Completeness Checklist

| Change | Must include |
| --- | --- |
| FSNP encoding or behaviour | Golden test in `internal/fsnp` or `internal/game`; design-doc wire-contract update; verified against `netplay.c` at `v3.1.66` |
| Lobby API | Go tests, Python client tests, contract test, README API section |
| Config keys or hash | Both hash implementations, regenerated `config-hash.json`, both suites green |
| Server flag | Flag + env var, README table, `Server.py` if passed by the launcher |
| Panel / UI state | Worker thread + `call_after` for I/O; all four themes; `fsui/test/test_qt6.py` |
| Rollout step finished | Design-doc Status line and Rollout entry updated |

## Verification beyond tests

Unit tests cannot prove a real emulator stays in sync. For protocol or timing changes, run a real session: `make -C fsnp-server`, then two `fs-uae v3.1.66` instances with `--netplay_server=127.0.0.1 --netplay_port=<port> --netplay_password=<pw> --netplay_tag=P1|P2`, and check the server log for `ping_ms`/`lag_ms` and no `mem`/`rnd` desync. Say so if you could not run one.
