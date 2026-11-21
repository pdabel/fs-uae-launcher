---
name: fsl-netplay
description: 'Rules and completeness checklists for netplay changes in FS-UAE Launcher: the FSNP v1 wire protocol, fsnp-server games and lobby, the lobby HTTP/session API, game listing, presence and auto-start, config sync and the shared config hash, Server.py spawning, and the Net Play tab. Use when adding or changing anything that crosses the launcher-to-server or server-to-emulator boundary.'
---

# Netplay Changes

Netplay has three parties and two contracts:

```text
launcher (Python)  --lobby HTTP / JSON-->  fsnp-server --lobby (Go)  <--FSNP v1 bytes--  fs-uae v3.1.66 (C)
```

Launchers find each other only through the lobbies in their `netplay_servers` list (plus *This computer* while the local lobby runs). There is no IRC and no chat channel; #164 removed them.

The **FSNP contract is fixed** by a C client this repo does not change. The **launcher-to-server contract is ours**, and both ends live in this repo, so both must change in the same commit or in server-first order.

Two design docs are the spec. Read the section for the area you touch before editing; they record measured behaviour and decisions that are not obvious from the code.

| Doc | Covers |
| --- | --- |
| `docs/netplay-go-server-design.md` | FSNP wire contract, the server, the lobby, the session API and config in the session (phase three) |
| `docs/netplay-rooms-design.md` | Lobby browser: the server list, `POST /lobby` listing and presence, Host game / Join, auto-start, the local lobby's lifecycle, security of listed games |

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

### Spawning the local lobby (`Server.py`)

**Host game** on *This computer* calls `Netplay.ensure_local_lobby()`, which starts `Server(port, 0, "", lobby=True, public_addresses=..., presence=True, name=...)` once and keeps it between games until **Stop lobby** or exit. The port is the `netplay_host_port` setting (default 25101), and hosting needs `netplay_public_address`.

`launcher/server/Server.py` spawns the binary found by `PluginExecutableFinder` (`"fsnp-server": "FS-UAE-Netplay-Server"`) with `--lobby`, `--exit-on-stdin-close`, `--log-file` and the lobby flags, then blocks on a helper thread for the stdout readiness line `{"event":"listening","port":N}`. It reads only `event` and `port`; new fields are additive. `PortInUseError` is a distinct `ServerError` so the panel can say what to do. `Server.stop()` closes stdin; `kill()` after `STOP_TIMEOUT` is the fallback. Single-game mode (no `--lobby`) is still in `Server.py` and the server, but the launcher no longer uses it.

| If you change... | Also change |
| --- | --- |
| A flag the launcher passes | `cmd/fsnp-server` flag + env var, `Server.py`, README flag table, `launcher/server/tests/test_server_start.py` |
| The readiness line | Keep `event`/`port` stable; extend only |
| Default port | 25101 (`HOST_PORT` in `lobby_servers.py`); the server's bind decides, not a launcher pre-check (a `SO_REUSEADDR`-less pre-check refused ports in `TIME_WAIT`) |
| When the local lobby stops | `game_running_in_local_lobby()` -- stopping it kills games being played |

### Lobby mode (`--lobby`, port 25101)

One port: `internal/lobby/sniff.go` reads the first four bytes -- `FSNP` goes to the password-hash router, `PING` gets `PONG`, anything else is replayed into the HTTP server. Every lobby game has a unique password because the password routes the connection.

The launcher uses the session API (`POST /game`, `GET /game/{id}`, players, config, ready, start, end) and the listing (`POST /lobby`); `fsnp-server/README.md` "API" has the shapes. `GET /game/create` is legacy and unused by the launcher.

| If you change... | Also change |
| --- | --- |
| An endpoint, status code, or JSON field | Go handler + tests, `launcher/netplay/lobby_client.py` + unit tests, the contract test against a real server, README "API" section |
| Session state transitions or auto-start | Go state machine tests, `launcher/netplay/session.py` and its tests, the panel that renders the state |
| The listing or presence (`POST /lobby`, `listing.go`) | Go listing tests, `lobby_browser.py` (`ServerWatcher`, `BrowsedGame`) and `test_lobby_browser.py`, the contract test |
| Auth (host token, player token) | Never log tokens; keep them out of the UI and the activity log; same commit on both sides |
| Timeouts (`--idle-timeout`, `--game-launch-timeout`, 25 s long-poll wait) | README table; the Python client's HTTP timeout must exceed the long-poll wait |
| Limits on names and titles (32 / 64 bytes) | Server check, launcher truncation (`truncate_utf8`, `MAX_TAG_LENGTH`) |

Compatibility: a lobby can be older or newer than a launcher. New request fields must default to the old behaviour (an absent `listed` means unlisted; an absent `auto_start` means manual start), and new response fields must be optional in `lobby_client.py`.

Order: server endpoint with tests first, then the client that calls it, so every commit in a stack works.

### Listed games and presence

- Anyone who can reach a lobby can see a listed game and claim a slot in it, and with the slot comes the config and the game password. Unlisted games are joined by ID only.
- Browsing sends the netplay name and a per-run member ID to every server in the list. Presence (`--presence`) is off by default on a lobby and on for the local lobby.
- Names, titles and lobby names come from other users: show them as plain text, never markup.
- Auto-start needs the host's own slot ready for the host's current config version, so a joiner can't start a game on a config the host didn't set.

---

## Config sync and the hash

| Piece | Location |
| --- | --- |
| Which keys travel (`sync`) and which are hashed (`checksum`) | `build_cfg()` in `launcher/launcher_config.py` -- the only vocabulary |
| Hash | `LauncherConfig.checksum_config()` (Python), `game.ConfigHash` (Go) |
| Golden cases | `fsnp-server/internal/game/testdata/config-hash.json`, read by `confighash_test.go` and `launcher/netplay/tests/test_checksum_golden.py` |
| Applying a host's config | `launcher/netplay/config_apply.py`: allowlist against sync keys; kickstarts and media by SHA-1 through the local file database; returns what could not be found |
| Keeping launchers in step | `launcher/netplay/session.py`: host pushes on every local sync-key change; everyone applies each new `config_version` and reports `{hash, missing}` |

Rules:

- The Go server never hardcodes Amiga keys. It is handed `keys: {sync, checksum}` and treats keys and values as opaque strings.
- A change to the hash (algorithm, key order, empty-value handling) changes both implementations and the fixture in one commit. A Python-only or Go-only hash change is a desync waiting for a real session.
- Values from a peer are data. They are never used as file paths, commands, or format strings; files are looked up by SHA-1 only.
- An empty kickstart SHA-1, main or extension, means the host has none set: it is cleared locally (the launch then uses the internal ROM) and not reported missing. `Amiga.INTERNAL_ROM_SHA1` for the main kickstart also means the internal ROM.
- A missing media file clears its slot rather than keeping a different disk; a missing kickstart leaves the current one in place. Both are reported in `missing`.

`fsnp-server/compose.yaml` is the reference lobby deployment.

---

## Completeness Checklist

| Change | Must include |
| --- | --- |
| FSNP encoding or behaviour | Golden test in `internal/fsnp` or `internal/game`; design-doc wire-contract update; verified against `netplay.c` at `v3.1.66` |
| Lobby API | Go tests, Python client tests, contract test, README API section |
| Config keys or hash | Both hash implementations, regenerated `config-hash.json`, both suites green |
| Server flag | Flag + env var, README table, `compose.yaml` comment if it's deployment-facing, `Server.py` if passed by the launcher |
| Netplay setting | `launcher/option.py` / `launcher_settings.py`, the Net Play settings page, migration for saved settings |
| Net Play tab / UI state | Worker thread + `call_after` for I/O; every launcher theme; the `test_lobby_browser_panel*` tests in `fsui/test/test_qt6.py` |
| Rollout step finished | The matching design doc's Status line and Rollout entry updated |

## Verification beyond tests

Unit tests cannot prove a real emulator stays in sync. For protocol or timing changes, run a real session: `make -C fsnp-server`, then two `fs-uae v3.1.66` instances with `--netplay_server=127.0.0.1 --netplay_port=<port> --netplay_password=<pw> --netplay_tag=P1|P2`, and check the server log for `ping_ms`/`lag_ms` and no `mem`/`rnd` desync. Say so if you could not run one.
