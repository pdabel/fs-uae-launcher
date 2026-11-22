# fsnp-server

The FS-UAE netplay server: a static Go binary that speaks FSNP v1, the protocol of the `fs-uae v3.1.66` netplay client, byte for byte. It replaced `launcher/server/game.py`. The design, the wire protocol and the history are in [docs/netplay-go-server-design.md](../docs/netplay-go-server-design.md).

It runs in one of two modes:

| Mode | Started by | Hosts |
|---|---|---|
| **single game** (default for the binary) | you, for one fixed game | one game, then exits |
| **lobby** (`--lobby`, default for the image) | you, on a machine players can reach, or the launcher's **Host game** on *This computer*, via `launcher/server/Server.py` | many games, created by launchers' **Host game**, until stopped |

## Running a lobby

```sh
docker run -d --name fs-uae-netplay -p 25101:25101 ghcr.io/pdabel/fs-uae-netplay:<version>
```

Tags: `latest` is the newest release, `<version>` a specific one (`3.2.0`, without the `v`), and `edge` the current `main`, which is never `latest`. Each runs on `linux/amd64`, `linux/arm64` and `linux/arm/v7`, so a Raspberry Pi can host a lobby.

That's the only port: the HTTP API and every game share **25101**. The server looks at the first four bytes of each connection. HTTP goes to the API, `PING` gets `PONG` (the launcher's connection test), and an FSNP handshake goes to the game its password names. So behind a router you forward one TCP port, not a range.

Players add `lobby.example.org` (or `host:port`, if it isn't on 25101) to their lobby servers in the launcher's Settings → Net Play. Their Net Play tab then lists every game waiting on it. **Host game** creates one there, **Join** takes a slot, and the game starts by itself once every player is ready. Set `LOBBY_NAME` to give the lobby a name in their lists, and `PRESENCE=1` to show them who else is browsing it.

### Passwords

**Every lobby game has a password, and no two live games share one**, because the password is how a connection finds its game:

- If none is given, the lobby generates one (8 characters), as it does for every game a launcher hosts. The players never type it: it reaches their launchers in the game's config.
- If a given password collides with a live game's, `/game/create` refuses it with `409`. Pick another.

Once a game ends, its password is free again.

### Settings

Each flag can also be set through its environment variable, which is how you configure the image (`-e NAME=value`).

| Flag | Env | Default | |
|---|---|---|---|
| `--lobby` | `LOBBY` | `false` (`true` in the image) | lobby mode |
| `--host` | `HOST` | `0.0.0.0` | address to listen on |
| `--port` | `PORT` | `25101` | the one port, for the API and all games |
| `--max-games` | `MAX_GAMES` | `64` | live games at once. Beyond that, `/game/create` returns `503` |
| `--game-launch-timeout` | `GAME_LAUNCH_TIMEOUT` | `900` | seconds a running game may wait for all its players before it's removed. A `/game/create` game runs from creation; a `POST /game` game from its start |
| `--idle-timeout` | `IDLE_TIMEOUT` | `600` | seconds a `POST /game` game may sit untouched (no join, config, ready or poll) before it starts |
| `--public-addresses` | `PUBLIC_ADDRESSES` | — | comma-separated addresses to give players. Unset, they get the host name the game's creator reached the lobby by |
| `--name` | `LOBBY_NAME` | — | a name shown to launchers browsing the lobby's games |
| `--presence` | `PRESENCE` | `false` | show launchers browsing the lobby who else is browsing it. Off by default so a public lobby doesn't show strangers' names |
| `--log-file` | `LOG_FILE` | — | also append the log here |
| `--log-input` | — | `true` | log every relayed input event |
| `--verbose` | — | `false` | debug logging |

Set `PUBLIC_ADDRESSES` when players should be given a different address from the one the host used, for example a public IP when the host is on the same LAN as the server. If a NAT or Docker maps an outside port to 25101, players are told the outside port, because the lobby reports the port as the host's request saw it.

The image runs as uid 101 in a `scratch` image, so `LOG_FILE` must point into a volume that uid can write to. Without it, `docker logs` shows everything.

### API

```
GET /game/create?players=N&password=P
  200  id=…&password=…&port=…&addresses=…      (form-encoded)
  400  bad players (1–6) or password over 128 bytes
  409  password already used by a live game
  503  too many games, or shutting down
GET /healthz
  200  ok
```

`/game/create` games run at once and have no session; the launcher no longer uses them. The session API is what it uses: the lobby holds each game's config and who has applied it (phase three of [the design](../docs/netplay-go-server-design.md#future-the-session-owns-the-config)). JSON in and out; calls marked *host* or *slot* need `Authorization: Bearer <token>` from the create or join reply. A `POST /game` game's password is reserved at once but reaches no emulator until `start`.

The host launcher publishes the initial config before announcing the game to other players. Later config edits continue to replace the server document through `PUT /game/{id}/config`.

If the host's local checksum does not match the lobby document after applying it, the launcher reports differing checksum key names without logging their values.
When applying the host's config changes a sync value, the updated config is published even if media is missing; unresolved media hashes remain in the document until changed by the host.

```
POST   /game                          {players, password, tag, keys:{sync, checksum}, listed, title, auto_start}
  201  {id, password, players, port, addresses, host_token, slot: 0, player_token}
GET    /game/{id}[?since=revision]    snapshot (with title, listed, auto_start); with since, waits up to 25 s for a change
POST   /game/{id}/players             {tag} → 201 {slot, player_token}; 409 when full
DELETE /game/{id}/players/{n}         slot or host: free a slot
PUT    /game/{id}/config              host: {config:{key: value}} → {config_version, hash}
POST   /game/{id}/players/{n}/ready   slot: {config_version, hash, missing:{key: sha1}}
POST   /game/{id}/start               host: 409 unless every slot is ready (an auto_start game starts itself)
DELETE /game/{id}                     host: end it
POST   /lobby                         {member, name, since} → {id, name, revision, presence, online, games:[…]}; with since, waits up to 25 s

errors {"error": "…"}: 400 invalid, 403 wrong token, 404 no game or slot,
       409 wrong state for the call, 503 too many games or shutting down
```

A game created with `"auto_start": true` starts by itself on the ready report that makes every slot claimed and ready for the current config. That includes the host's own slot, so a joiner can't start a config the host didn't set. Without the field the host calls `start`, as before.

`POST /lobby` is what the launcher's Net Play browser polls. It lists the games created with `"listed": true`, from creation until they end: each one's `id`, `title`, `host` (slot 0's tag), `state`, `players`, `joined` and `created`. It carries no passwords, tokens, configs or addresses; joining still goes through `POST /game/{id}/players`. A game is unlisted when `listed` is absent, so older launchers' games stay private. The lobby's `id` is random per run, so a launcher that reaches one lobby at two addresses can tell. With `--presence`, a caller that sends a `member` (a random id per launcher run) and a `name` counts as online while it has a poll open or had one answered in the last 35 s, and `online` lists those names. Without it, `presence` is `false`, `online` is absent and `member` and `name` are ignored. At most 256 members are tracked; past that, `503`. See [the lobby browser design](../docs/netplay-rooms-design.md).

## With Docker Compose

[compose.yaml](compose.yaml) runs the lobby with its settings in one file:

```sh
docker compose up -d          # from this directory
```

Forward TCP **25101** to the machine. The lobby is built from this checkout. To use a published image instead, swap `build:` for `image:` as the file's comment says. `LOBBY_PORT=… docker compose up -d` publishes the lobby on another host port; players then add `host:port` to their server lists.

## A single fixed game

```sh
docker run -d -p 25101:25101 -e LOBBY=false -e PLAYERS=2 -e PASSWORD=secret ghcr.io/pdabel/fs-uae-netplay:<version>
```

This is the image's old behaviour. One game waits on 25101, and the container exits when it ends. The launcher doesn't create games this way any more. Single-game settings are `--players`/`PLAYERS`, `--password`/`PASSWORD` and `--launch-timeout`/`LAUNCH_TIMEOUT` (seconds, `0` = wait forever).

## Development

```sh
make          # build ./fsnp-server, where the launcher looks for it in development mode
make check    # gofmt, go vet, go test -race
make help     # everything else
```

No local Go install is needed: without `go` on `PATH`, `make` runs the same commands in a `golang` container.

To build directly with Go instead, install it first if needed:

- **Debian/Ubuntu:** `sudo apt install golang-go`
- **macOS with Homebrew:** `brew install go`
- **Without a package manager:** use the installer for your operating system
  from [the Go downloads page](https://go.dev/dl/). On macOS, choose the package
  matching your Mac (Apple Silicon/ARM64 or Intel/x86-64).

Then run the `go build` command below.

### Launcher startup errors

When **Host game** on *This computer* cannot find or launch the server, it
reports an error in the Net Play tab's activity log and hosts nothing:

- **Executable not found:** in a source checkout, run `make` in this directory,
  or `go build -o fsnp-server ./cmd/fsnp-server` with Go installed. This creates
  `fsnp-server/fsnp-server` relative to the repository root. The source directory
  itself is not an executable. For a packaged launcher, reinstall the netplay
  server or the launcher package that includes it.
- **Permission denied:** check the reported executable's permissions and whether
  its filesystem allows execution. On Linux/macOS, a trusted server binary may
  need its execute bit restored with `chmod u+x <path-to-binary>`; changing the
  source directory's permissions will not build the binary.
- **Missing executable/loader or invalid executable format:** rebuild or
  reinstall the server for your operating system and CPU architecture.

Launch errors include the executable path and the operating-system error.
Source checkouts also show the command to build the server.
