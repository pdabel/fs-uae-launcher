---
name: fsl-structure
description: 'FS-UAE Launcher architecture: package roles, layer boundaries, the launch pipeline, and the netplay launcher-to-server flow. Use when exploring the codebase, tracing how a setting reaches FS-UAE, tracing a netplay game from /hostgame or /startgame to the emulator, or deciding where a change belongs.'
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
  settings/                     Settings dialog pages
  netplay/
    irc.py, channel.py          IRC connection and channels (oyoyo); chat only once config moves to the lobby
    netplay.py                  Netplay controller: commands (/hostgame, /startgame), game lifecycle
    config_apply.py             Apply a host's config document: allowlist, resolve files by SHA-1
    netplay_panel.py            Netplay UI
    tests/                      pytest; includes golden and contract tests
  server/Server.py              Spawns the bundled fsnp-server, waits for its readiness line
fsgs/                           Game-system layer
  amiga/                        FS-UAE driver, config writer, ROM handling, WHDLoad
  plugins/pluginexecutablefinder.py   Finds fs-uae and fsnp-server (known_executables)
  FSGSDirectories.py            Base/cache/logs directories
fsui/                           Widget toolkit over Qt; fsui/qt is the only Qt import surface
fsbc/                           application (call_after, threads), logging, paths, Signal, settings
fstd/, fspy/, fsboot/           Small utilities; fsboot locates base and executable dirs
workspace/                      Workspace UI support
amitools/                       Amiga filesystem and ROM tools (vendored)
oyoyo/                          IRC client library (vendored)
fsnp-server/                    Go module, standard library only
  cmd/fsnp-server/              Flags/env, signals, readiness line, single-game vs --lobby
  internal/fsnp/                FSNP v1 codec, password hash, handshake; golden tests in testdata/
  internal/game/                One game: tick loop, conns, sync check, ConfigHash
  internal/lobby/               Port-25101 sniffer, password router, registry, HTTP API
fsbuild/                        Packaging scripts (build, bundle, archive, sign, notarize)
docs/                           Design docs; netplay-go-server-design.md is the netplay spec
po/                             Translations; po-update.py extracts strings
```

Phase three of netplay (config held by the lobby session) adds `launcher/netplay/lobby_client.py`, `launcher/netplay/session.py`, and `fsnp-server/internal/lobby/session.go` + `api.go`. Check the design doc's Rollout section for what has landed.

---

## Layers

| Layer | Package(s) | Owns |
| --- | --- | --- |
| UI | `launcher/ui/`, `launcher/panels/`, `launcher/settings/`, `launcher/netplay/*_panel.py`, `fsui/` | Widgets, themes, user input; renders state |
| Config model | `launcher/launcher_config.py`, `launcher/launcher_settings.py` | Current config values, change signals, key tags, the config hash |
| Game system | `fsgs/` | File/game databases, executable lookup, turning a config into an FS-UAE run |
| Netplay client | `launcher/netplay/` (non-UI), `launcher/server/` | IRC, lobby HTTP, applying a host's config, spawning the local server |
| Netplay server | `fsnp-server/` | FSNP framing and timing, games, lobby, session config documents |
| Base | `fsbc/`, `fstd/`, `fspy/`, `fsboot/` | Threading, logging, paths, signals |

**Boundary rules:**

- UI renders state and calls into the model or netplay client; it does not do network or disk I/O on the Qt thread.
- Netplay client code reaches the UI through signals or `call_after`, not by holding widgets.
- `config_apply.py` stays pure: dependencies (file lookup, config setter) come in as arguments, so it is unit-testable.
- The Go server takes the key list from the launcher and treats config keys and values as opaque strings.
- Base packages already import upward in places (`fsbc/logging.py`, `fsbc/paths.py`, `fsbc/settings.py` reach into `fsgs`/`launcher`). Don't add more; new shared helpers that need launcher state belong in `launcher/` or `fsgs/`.
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
IRC channel (chat, finding each other)            [launcher/netplay/irc.py, channel.py]
  op: /hostgame
     -> Server.start()                               [launcher/server/Server.py]
        spawns fsnp-server --exit-on-stdin-close --log-file=<logs>/fsnp-server.log.txt
        reads stdout until {"event":"listening","port":N}
  op: /startgame <host>[:port]
     -> lobby on <host>:25101 creates the game
  config: the host's sync keys -> each player's launcher
        IRC era: one __config privmsg per key, __prestart/__ackstart/__start handshake
        Lobby era: PUT /game/{id}/config, players long-poll GET /game/{id}, POST .../ready
                   with {hash, missing}; host POST /start opens the FSNP game
  each player: apply_config() -> allowlisted keys set, files resolved by SHA-1
             -> checksum_config() compared with the host's / server's hash
  start: every launcher starts fs-uae with the game's address, port, password, tag
fsnp-server (port 25101: first four bytes pick FSNP / PING / HTTP)
  -> lobby routes FSNP by password hash to the game
  -> game ticks every 20 ms, relays input events, checks MEM/RND checksums
```

---

## Generated or Vendored -- edit with care

| Path | Status |
| --- | --- |
| `launcher/option.py`, `fsgs/option.py`, `launcher/ui/config/expand.py` | Headers say "Automatically generated". The generator is not in this repo, so edits are by hand; keep the existing format exactly |
| `oyoyo/`, `amitools/` | Vendored third-party code; patch minimally and say so in the commit |
| `fsnp-server/internal/fsnp/testdata/*.bin` | Captured from a real session; never hand-edit |
| `fsnp-server/internal/game/testdata/config-hash.json` | Golden cases shared by Go and Python |
| `Pipfile.lock` | Regenerated by pipenv or Dependabot, never by hand |

## Directories at Runtime

| What | Where |
| --- | --- |
| Logs | `FSGSDirectories.get_logs_dir()` -> `<base>/Cache/Logs` unless portable; launcher log and `fsnp-server.log.txt` |
| Dev-mode `fsnp-server` | `fsnp-server/fsnp-server`, built by `make -C fsnp-server` |
| Packaged `fsnp-server` | Next to the PyInstaller output, built by `fsbuild/build.sh` |
