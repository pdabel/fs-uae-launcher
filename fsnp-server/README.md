# fsnp-server

The FS-UAE netplay server: a static Go binary that speaks FSNP v1, the protocol of the `fs-uae v3.1.66` netplay client, byte for byte. It replaced `launcher/server/game.py`. The design, the wire protocol and the history are in [docs/netplay-go-server-design.md](../docs/netplay-go-server-design.md).

It runs in one of two modes:

| Mode | Started by | Hosts |
|---|---|---|
| **single game** (default for the binary) | the launcher's `/hostgame`, via `launcher/server/Server.py` | one game, then exits |
| **lobby** (`--lobby`, default for the image) | you, on a machine players can reach | many games, created by the launcher's `/startgame`, until stopped |

## Running a lobby

```sh
docker run -d --name fs-uae-netplay -p 25101:25101 ghcr.io/pdabel/fs-uae-netplay:<version>
```

That's the only port: the HTTP API and every game share **25101**. The server looks at the first four bytes of each connection. HTTP goes to the API, `PING` gets `PONG` (the launcher's connection test), and an FSNP handshake goes to the game its password names. So behind a router you forward one TCP port, not a range.

From the launcher, an op in the game channel runs:

```
/startgame lobby.example.org
```

That asks the lobby for a game for the channel's player count. The players' launchers receive the game's address, port and password through the channel, as with any other netplay game, and connect when the game starts. `/startgame <host>[:<port>] [<players>] [<password>]` sets the rest explicitly.

### Passwords

**Every lobby game has a password, and no two live games share one**, because the password is how a connection finds its game:

- If none is given, the lobby generates one (8 characters). The players never type it: it reaches their launchers through the channel.
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
| `--game-launch-timeout` | `GAME_LAUNCH_TIMEOUT` | `900` | seconds a game may wait for all its players before it's removed |
| `--public-addresses` | `PUBLIC_ADDRESSES` | — | comma-separated addresses to give players. Unset, they get the host name the op used in `/startgame` |
| `--log-file` | `LOG_FILE` | — | also append the log here |
| `--log-input` | — | `true` | log every relayed input event |
| `--verbose` | — | `false` | debug logging |

Set `PUBLIC_ADDRESSES` when players should be given a different address from the one the op used, for example a public IP when the op is on the same LAN as the server. If a NAT or Docker maps an outside port to 25101, players are told the outside port, because the lobby reports the port as the op's request saw it.

The image runs as uid 101 in a `scratch` image, so `LOG_FILE` must point into a volume that uid can write to. Without it, `docker logs` shows everything.

### API

```
GET /game/create?players=N&password=P
  200  id=…&password=…&port=…&addresses=…      (form-encoded, what /startgame parses)
  400  bad players (1–6) or password over 128 bytes
  409  password already used by a live game
  503  too many games, or shutting down
GET /healthz
  200  ok
```

## Lobby and IRC together

Players' launchers also need an IRC server, where they meet in a game channel and the op's launcher sends everyone the game's config. [compose.yaml](compose.yaml) runs both:

```sh
docker compose up -d          # from this directory
```

Forward TCP **25101** (lobby and games) and **6667** (IRC) to the machine, and set the launcher's IRC server (Settings → Netplay) to its address.

**The IRC server needs its flood limits relaxed, and the compose file does that** by mounting [irc/netplay.conf](irc/netplay.conf). The launcher sends the config as one message per setting, back to back, and resends it whenever a player joins. On InspIRCd's defaults that took about 40 seconds per sync, and a long config can get the op disconnected. If you run a different IRC server, give it the same allowance: a burst of a few hundred messages, and a receive queue of 64 KB.

The lobby is built from this checkout. To use a published image instead, swap `build:` for `image:` as the file's comment says. `LOBBY_PORT=… docker compose up -d` publishes the lobby on another host port. Players are told the port the op's `/startgame` used, so that works without further changes. IRC has to stay on 6667, because that's the only port the launcher connects to.

## A single fixed game

```sh
docker run -d -p 25101:25101 -e LOBBY=false -e PLAYERS=2 -e PASSWORD=secret ghcr.io/pdabel/fs-uae-netplay:<version>
```

This is the image's old behaviour. One game waits on 25101, and the container exits when it ends. Point the launcher at it with `/customgame <host>:25101 2 secret`. Single-game settings are `--players`/`PLAYERS`, `--password`/`PASSWORD` and `--launch-timeout`/`LAUNCH_TIMEOUT` (seconds, `0` = wait forever).

## Development

```sh
make          # build ./fsnp-server, where the launcher looks for it in development mode
make check    # gofmt, go vet, go test -race
make help     # everything else
```

No local Go install is needed: without `go` on `PATH`, `make` runs the same commands in a `golang` container.
