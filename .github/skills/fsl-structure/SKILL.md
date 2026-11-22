---
name: fsl-structure
description: 'FS-UAE Launcher architecture: package roles, layer boundaries, the launch pipeline, and the netplay launcher-to-server flow. Use when exploring the codebase, tracing how a setting reaches FS-UAE, tracing a netplay game from Host game or Join in the Net Play tab to the emulator, or deciding where a change belongs.'
---

# FS-UAE Launcher Architecture and Structure

## Repository Layout

```text
fs-uae-launcher                 Entry script; fsboot init, then dispatches through launcher.apps
launcher/
  launcherapp.py                App startup, starting games (writes netplay_* options for fs-uae)
  launcher_config.py            LauncherConfig: the current config; build_cfg() sync/checksum tags;
                                checksum_config()
  launcher_settings.py          Persistent launcher settings
  option.py                     Option metadata table (header says generated; generator is not in this repo)
  ui/                           Main window, config browser, dialogs, skin/themes
  panels/                       Config editor pages (floppies, ROM/RAM, input, ...)
  settings/                     Settings dialog pages; netplay_settings_page.py + lobby_servers_group.py
                                hold the netplay name, lobby server list, public address and host port
  netplay/
    netplay.py                  Netplay controller: browsing, join_game, host_game, the local lobby, activity log
    lobby_servers.py            netplay_servers setting (";"-separated host[:port]); default port 25101
    lobby_browser.py            ServerWatcher (one long-poll thread per lobby), LobbyBrowser (merged game list)
    lobby_client.py             LobbyClient (session API over HTTP), SessionWatcher (long-poll GET /game/{id})
    session.py                  NetplaySession: one game, hosting or joined; push/apply config, report ready, launch
    config_apply.py             Apply a host's config document: allowlist, resolve files by SHA-1
    connection_tester.py        Finds which of a game's addresses reaches its server (sets __netplay_host)
    netplay_page.py, lobby_browser_panel.py   The Net Play tab: servers, games, Host game / Join dialogs, activity log
    tests/                      pytest; includes golden and contract tests (conftest.py builds fsnp-server)
  server/Server.py              Spawns the bundled fsnp-server --lobby, waits for its readiness line
fsgs/                           Game-system layer
  amiga/                        FS-UAE driver, config writer, ROM handling, WHDLoad
  plugins/pluginexecutablefinder.py   Finds fs-uae and fsnp-server (known_executables)
  FSGSDirectories.py            Base/cache/logs directories
fsui/                           Widget toolkit over Qt; fsui/qt is the only Qt import surface
fsbc/                           application (call_after, threads), logging, paths, Signal, settings
fstd/, fspy/, fsboot/           Small utilities; fsboot locates base and executable dirs
workspace/                      Workspace tool windows (ADF/HDF creators, joystick config, login)
fsnp-server/                    Go module, standard library only
  cmd/fsnp-server/              Flags/env, signals, readiness line, single-game vs --lobby
  internal/fsnp/                FSNP v1 codec, password hash, handshake; golden tests in testdata/
  internal/game/                One game: tick loop, conns, sync check, ConfigHash
  internal/lobby/               Port-25101 sniffer, password router, registry, session API (session.go,
                                api.go), game listing and presence (listing.go)
  compose.yaml                  Reference lobby deployment
fsbuild/                        Packaging scripts (build, bundle, archive, sign, notarize)
docs/                           architecture.md (launcher map); netplay-go-server-design.md (server and
                                protocol spec); netplay-rooms-design.md (lobby browser)
po/                             Translations; po-update.py extracts strings
```

`docs/architecture.md` has Mermaid diagrams of the package dependencies and startup sequence; read it before moving code between packages.

---

## Layers

| Layer | Package(s) | Owns |
| --- | --- | --- |
| UI | `launcher/ui/`, `launcher/panels/`, `launcher/settings/`, `launcher/netplay/*_panel.py`, `launcher/netplay/netplay_page.py`, `fsui/` | Widgets, themes, user input; renders state |
| Config model | `launcher/launcher_config.py`, `launcher/launcher_settings.py` | Current config values, change signals, key tags, the config hash |
| Game system | `fsgs/` | File/game databases, executable lookup, turning a config into an FS-UAE run |
| Netplay client | `launcher/netplay/` (non-UI), `launcher/server/` | Browsing lobbies, lobby HTTP, the game session, applying a host's config, spawning the local lobby |
| Netplay server | `fsnp-server/` | FSNP framing and timing, games, lobby, listing and presence, session config documents, auto-start |
| Base | `fsbc/`, `fstd/`, `fspy/`, `fsboot/` | Threading, logging, paths, signals |

**Boundary rules:**

- UI renders state and calls into the model or netplay client; it does not do network or disk I/O on the Qt thread.
- Netplay client code reaches the UI through listeners and `call_after`, not by holding widgets. `Netplay` exposes `session_listeners`, `browser_listeners` and `activity_listeners`; `NetplaySession` and `LobbyBrowser` take `dispatch`/`on_change` callables, so tests run them without Qt.
- `config_apply.resolve_config` stays pure: dependencies (file lookup, sync keys) come in as arguments, so it is unit-testable. `apply_config`/`apply_document` are the thin wrappers that touch `LauncherConfig`.
- The Go server takes the key list from the launcher and treats config keys and values as opaque strings.
- Base packages don't import upward: `fsbc` imports nothing above it, and `fsui` and `fsgs` import neither each other nor `launcher`/`workspace`. A `test_layering.py` in each enforces it. Pass in what a base package needs (as `initialize_application()` does) instead of importing it; helpers that need launcher state belong in `launcher/`.
- All Qt imports go through `fsui.qt` (QtPy over PySide6).

---

## Launch Pipeline

```text
User picks a game / edits config
  -> LauncherConfig.set(key, value)                 [launcher/launcher_config.py]
       change signals update panels
  -> Start
  -> launcherapp.py start path                       [launcher/launcherapp.py]
       netplay games: copies __netplay_* keys into fs-uae netplay_server/port/password/tag
  -> fsgs Amiga driver writes an FS-UAE config       [fsgs/amiga/]
  -> PluginExecutableFinder finds fs-uae             [fsgs/plugins/pluginexecutablefinder.py]
  -> fs-uae runs; for netplay it connects to fsnp-server over FSNP v1
```

## Netplay Flow

```text
Net Play tab opens -> Netplay.start_browsing()          [launcher/netplay/netplay.py]
  LobbyBrowser: one ServerWatcher per netplay_servers entry,  [lobby_browser.py]
    plus "This computer" over 127.0.0.1 while the local lobby runs
    each long-polls POST /lobby {member, name, since} -> listed games, presence
    listings reach the panel through call_after; servers de-duplicated by lobby id

Host game (dialog: server, players, listed)  -> Netplay.host_game()
  on This computer: ensure_local_lobby() -> Server(port, lobby=True, presence=True, ...).start()
      spawns fsnp-server --lobby --exit-on-stdin-close --log-file=<logs>/fsnp-server.log.txt
      reads stdout until {"event":"listening","port":N}       [launcher/server/Server.py]
  worker thread: POST /game {players, tag, keys:{sync, checksum}, listed, title, auto_start: true}
  follow_hosted_game(): __netplay_* keys set, NetplaySession with host_token

Join (or Join by ID...)  -> Netplay.join_game()
  worker thread: POST /game/{id}/players {tag} -> slot, player_token
  NetplaySession as a player

NetplaySession (one game, one worker thread for lobby calls)   [session.py]
  host: PUT /game/{id}/config whenever a sync key changes locally
  everyone: SessionWatcher long-polls GET /game/{id}?since=revision    [lobby_client.py]
            new config_version -> apply_document() -> allowlisted keys set,  [config_apply.py]
            files resolved by SHA-1 -> POST /game/{id}/players/{n}/ready {hash, missing}
  lobby: auto_start game starts once every slot (host's included) is ready for the current version
  state "running": launch_session_game() -> ConnectionTester's verified address in __netplay_host
                   -> launcher start path -> fs-uae with address, port, password, tag

fsnp-server --lobby (one port, 25101: first four bytes pick FSNP / PING / HTTP)
  -> lobby routes FSNP by password hash to the game
  -> game ticks every 20 ms, relays input events, checks MEM/RND checksums
```

There is no chat and no IRC: #164 removed both, along with `oyoyo/`. The legacy `GET /game/create` endpoint still exists in the server but the launcher doesn't use it.

---

## Generated, Captured or Locked -- edit with care

| Path | Status |
| --- | --- |
| `launcher/option.py`, `fsgs/option.py`, `launcher/ui/config/expand.py` | Headers say "Automatically generated". The generator is not in this repo, so edits are by hand; keep the existing format exactly |
| `fsnp-server/internal/fsnp/testdata/*.bin` | Captured from a real session; never hand-edit |
| `fsnp-server/internal/game/testdata/config-hash.json` | Golden cases shared by Go and Python |
| `Pipfile.lock` | Regenerated by pipenv or Dependabot, never by hand |

## Directories at Runtime

| What | Where |
| --- | --- |
| Logs | `FSGSDirectories.get_logs_dir()` -> `<base>/Cache/Logs` unless portable; launcher log and `fsnp-server.log.txt` |
| Dev-mode `fsnp-server` | `fsnp-server/fsnp-server`, built by `make -C fsnp-server` |
| Packaged `fsnp-server` | Next to the PyInstaller output, built by `fsbuild/build.sh` |
