# Netplay Lobby Browser

Design proposal for finding, setting up and joining netplay games without IRC. The launcher keeps a list of lobby servers. When the Net Play tab opens it connects to all of them and shows every game waiting for players. Pick one and join it, or host your own. A game starts by itself once every player has joined with the right config.

| | |
|---|---|
| **Status** | Implemented, and IRC removed |
| **Date** | 2026-11-21 (replaces the 2026-10-25 *rooms* draft) |
| **Builds on** | [netplay-go-server-design.md](netplay-go-server-design.md): the lobby, the session API and config in the session (phase three) |
| **Scope** | A server list in settings. A netplay panel that browses, hosts and joins games. `fsnp-server` gains a game listing, presence and auto-start |
| **Not in scope** | Removing IRC (a later step). Chat, which already happens on Discord |

## Contents

1. [Summary](#summary)
2. [Why](#why)
3. [What changed from the rooms draft](#what-changed-from-the-rooms-draft)
4. [The concept](#the-concept)
5. [UX](#ux)
6. [Lobby API](#lobby-api)
7. [Polling and unresponsive servers](#polling-and-unresponsive-servers)
8. [Launcher changes](#launcher-changes)
9. [Security](#security)
10. [Rollout](#rollout)
11. [Alternatives considered](#alternatives-considered)
12. [Decisions](#decisions)
13. [Follow-ups pending feedback](#follow-ups-pending-feedback)

## Summary

Think of a games lobby. You want to play Sensible Soccer, you open Net Play, and you can see whether anyone already has a game waiting. If nobody does, you host one and wait for someone to join.

- **Settings → Net Play** holds a list of lobby servers (`host[:port]`), added and removed like the scan paths list.
- **Opening the Net Play tab** connects to every server in the list, each watched on its own so a slow or dead server doesn't hold up the rest. If this computer is running a lobby, it's watched too, without needing to be in the list.
- **The panel** shows each server's status and one combined list of games: title, host, players and server. If a server reports who's online, the panel shows them too, and lobbies hosted on a player's computer always do.
- **Join** claims a slot in the chosen game through the existing session API. From there it's the session flow we already have: the config is applied, files are checked and readiness is reported.
- **Host game** creates a game for the loaded config on a chosen server, or on this computer. Games are listed unless you untick *List this game*.
- **The game starts by itself** once every slot is claimed and every player reports the host's config as applied with nothing missing. Nobody presses Start.

## Why

- **Finding a game needs IRC today.** A launcher learns about a game only when an IRC op announces `__session <lobby> <game_id>` in the channel it's sitting in. If you're not in that channel at that moment, you don't see the game.
- **The lobby already knows every game.** Since phase three it holds each session's slots, config and state. It just has no way to list them.
- **More than one group plays.** A launcher that can watch several lobbies covers a club server, a friend's computer and your own, without one shared IRC network.
- **Starting by hand only waits for the host.** The lobby already knows when every slot is ready (state `ready`). Today the host still has to notice that and type `/startgame`.

## What changed from the rooms draft

The earlier draft paired launchers through a secret *room key*. Each room had at most one current game, and the game joined automatically. We've moved away from it:

| Rooms draft | This proposal |
|---|---|
| One lobby, one room key, shared privately | Any number of lobby servers, listed in settings |
| You see the people you've paired with | You see every listed game on the servers you've added, and who's online in lobbies hosted on a player's computer |
| The room's game is joined automatically | You pick a game and press **Join** |
| One current game per room | Any number of games per server |
| The host presses **Start game** | The game starts once every player is ready |

Rooms remain an option for later if private groups on a shared server turn out to matter (see [Alternatives considered](#alternatives-considered)).

## The concept

### Servers

- A server is an `fsnp-server` running in lobby mode, the same Docker image or binary as now. Its entry is `host` or `host:port`, and the port defaults to 25101.
- The list lives in a new `netplay_servers` setting, `;`-separated like `search_path`. It starts empty.
- A server can optionally name itself (`--name "Amiga Friday"`). The panel shows that name next to the address.

### This computer

Hosting on this computer is what `/hostgame` does today: the launcher runs `fsnp-server` in lobby mode, and players connect to this machine's public address.

**This computer's lobby doesn't need to be in your server list.** While it's running, the browser watches it automatically, as **This computer**, over loopback (`127.0.0.1`). This is the recommendation, chosen over requiring an entry in the list because:

- **Your public address often can't be reached from inside your own network.** Many home routers don't support NAT hairpinning, so an entry with your own public address would show *can't reach* even while your lobby is running fine. Loopback always works.
- **No stale entry.** When you're not hosting, there's nothing in the list showing as unreachable.
- **Nothing to set up for the person who's hosting.** Only the other players add your public address to their lists, once, and the panel has a **Copy address** button to share it.

If your list also has your own public address in it, the lobby's per-run `id` (see [Lobby API](#lobby-api)) lets the browser show it as the same server instead of listing the server twice.

The lobby on this computer starts when you first host on it. It keeps running between games while the launcher is open, so friends' launchers don't flicker to *can't reach* between rounds. It stops when you press **Stop lobby** or close the launcher, but not while a game in it is still running. That last rule is today's `release_hosted_server` behaviour.

The address players use is a setting (*Players reach this computer at*), replacing the address argument to `/hostgame`.

### Games

- **Listed by default.** A game appears in the list unless its host unticks *List this game* (`"listed": false` on `POST /game`). The lobby's default is unlisted when the field is absent, so games from older launchers stay unlisted and work exactly as now.
- **What's shown.** The list shows games waiting for players (`created`, `configuring`, `ready`) and games that are `running`. Running games are greyed out because there's no slot to join. Ended games drop off.
- **Each entry** has a title (the host's loaded config name), the host's name, the slots taken out of the total, and the server.
- **Unlisted games** are joined by ID. The host copies it from the panel, and others use **Join by ID…**, which is today's `/joingame`.

### Joining

- **Join** is `POST /game/{id}/players`, the same request an IRC announcement triggers today. The joining code is shared, not duplicated: `on_session_announce` becomes a thin wrapper around a new `join_game(host, port, game_id)`.
- You're in at most one game at a time. Joining another game, or pressing **Leave**, frees your slot first.

### Hosting

- **Host game** takes the loaded config, a server (any online entry in your list, or **This computer**), the number of players and *List this game*. It's disabled with no config loaded, with the tooltip "Choose a game first".
- The host holds slot 0 and reports readiness like any other player, as now. Config changes the host makes in the normal UI reach everyone as they do now, and resetting readiness makes players re-check.
- The host can **End game** at any time before it starts.

### Starting

- **When.** A game created with `"auto_start": true` starts in the lobby when it reaches `ready`. That means every slot is claimed and every player has reported the current config version applied, with the same hash and nothing missing. The check happens under `l.mu` in `reportReady`, the only call that can complete readiness: joining adds a slot that isn't ready yet, and a config change resets readiness.
- **What follows.** The game's state goes to `running` and every launcher's `SessionWatcher` sees it. They launch FS-UAE through the existing `launch_session_game`, exactly as after a manual start.
- **Manual start.** `POST /game/{id}/start` stays for games created without `auto_start`, which covers the IRC `/startgame` path and older launchers.

## UX

Wireframes are for layout and wording, not pixels.

### Settings → Net Play

```
┌─ Net Play ────────────────────────────────────────────────────────────┐
│                                                                       │
│  Netplay name   [ Paul                              ]                 │
│                                                                       │
│  Lobby servers                                                        │
│  ┌──────────────────────────────────────────────────┐   [ + ]         │
│  │ netplay.example.net                              │   [ − ]         │
│  │ 203.0.113.4:25200                                │                 │
│  │ old.example.org                                  │                 │
│  └──────────────────────────────────────────────────┘                 │
│  Connected to when the Net Play tab opens. Port defaults to 25101.    │
│                                                                       │
│  Hosting on this computer                                             │
│    Players reach this computer at [ 198.51.100.7      ]               │
│    Port [ 25101 ]   Forward this TCP port to this computer.           │
│                                                                       │
│  Tag            [ PAU ]                                               │
│  IRC server     [ irc.example.net                   ]                 │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

- **+** opens a one-line text dialog. The entry is checked with the existing `parse_lobby()` and normalised (lowercase host, `:25101` dropped). Duplicates are refused.
- **Netplay name** is the name other players see. It's used as the lobby tag on join and host, and for presence. On first run it's copied from `irc_nick`. *Tag* (the emulator's FSNP tag) and *IRC server* stay until IRC is removed.
- Changing the list while the Net Play tab is open applies straight away: removed servers stop being watched and new ones start.

### Net Play panel: browsing

```
┌─ Net Play ──────────────────────────────────────────────── (i) ───────┐
│                                                                       │
│  Servers                                                              │
│    ● Amiga Friday (netplay.example.net)              2 games          │
│    ● Dave's lobby (203.0.113.4:25200)                no games         │
│        Online: Dave, Sam, Paul (you)                                  │
│    ○ old.example.org     can't reach it, retrying in 40 s  [ Retry ]  │
│                                                                       │
│  Games                                                                │
│    Sensible Soccer     Kim     1 of 2     Amiga Friday     [ Join ]   │
│    Speedball 2         Lee     2 of 2     Amiga Friday       full     │
│    Turrican II         Ash     running    Amiga Friday                │
│                                                                       │
│  [ Host game: Sensible Soccer… ]   [ Join by ID… ]                    │
│                                                                       │
│  ── Activity ─────────────────────────────────────────────────────    │
│  20:14  Connected to Amiga Friday                                     │
│  20:14  Can't reach old.example.org: connection refused               │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

- Games are sorted with joinable games first, then by title.
- Games from a server that can't be reached are hidden, since they can't be joined anyway.
- *Online* appears under any server that reports presence, which a lobby on a player's computer always does.
- With no servers configured and no local lobby, the Servers section says *"No lobby servers yet"* and has an **Add a server…** button that opens Settings → Net Play. **Host game** still works with **This computer**.
- While IRC still exists, the panel sits above the channel area. Moving IRC out comes with its removal.

### Host game

The launcher asks the host to wait if a local CD checksum calculation is still
pending. CD selections and their SHA-1 metadata are published together when
the worker finishes, avoiding an intermediate empty hash in the session.

**Host game** opens a small dialog. The button names the loaded config, so it's clear what will be shared.

```
┌─ Host Sensible Soccer ──────────────────────────────┐
│                                                     │
│  Server    [ This computer (198.51.100.7)     ▾ ]   │
│  Players   [ 2 ▾ ]                                  │
│  [x] List this game                                 │
│                                                     │
│  Starts when every player has joined and is ready.  │
│                                                     │
│                          [ Cancel ]  [ Host ]       │
└─────────────────────────────────────────────────────┘
```

The server list holds **This computer**, plus every entry that's currently online. It defaults to the server used last time.

### Hosting on this computer

```
┌─ Net Play ──────────────────────────────────────────────── (i) ───────┐
│                                                                       │
│  Sensible Soccer, hosted by you on This computer                      │
│    1. Paul (you) — ready                                              │
│    2. (waiting for a player)                                          │
│                                                                       │
│  Online in your lobby: Dave, Sam                                      │
│  Players reach you at 198.51.100.7:25101    [ Copy address ]          │
│                                                                       │
│  [ End game ]   [ Stop lobby ]                                        │
│  Starts when 1 more player joins and is ready.                        │
│                                                                       │
│  ── Activity ─────────────────────────────────────────────────────    │
│  20:16  Lobby running on port 25101                                   │
│  20:16  Hosting Sensible Soccer for 2 players (listed)                │
│  20:17  Dave is online                                                │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

The bottom line says what the game is waiting for, using today's `waiting_on()`: *Starts when 1 more player joins and is ready.* or *Waiting: Dave is missing files.* For an unlisted game, a **Copy game ID** button appears next to **End game**.

### Joined

```
┌─ Net Play ──────────────────────────────────────────────── (i) ───────┐
│                                                                       │
│  Sensible Soccer, hosted by Paul on Dave's lobby                      │
│    1. Paul — ready                                                    │
│    2. Dave (you) — missing: Sensible Soccer.adf                       │
│                                                                       │
│  [ Re-check ]  [ Leave ]                                              │
│  Starts when you're ready: add the missing file, then Re-check.       │
│                                                                       │
│  ── Activity ─────────────────────────────────────────────────────    │
│  20:17  Joined Sensible Soccer as player 2                            │
│  20:17  Missing Sensible Soccer.adf. Add it, then press Re-check      │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

The slot lines are today's `slot_lines()`. When the last player reports ready, every launcher shows *Starting…* and launches FS-UAE. If the host ends the game, or it's reaped, the panel goes back to browsing with an activity line saying why.

## Lobby API

There's one new route, next to the session API in [api.go](../fsnp-server/internal/lobby/api.go). `POST /game` gains three fields.

```
POST /lobby    listed games and presence; long-polls past revision
POST /game     existing; gains optional "listed", "title" and "auto_start"
```

`POST /lobby` takes a request body so that presence can identify the caller:

```json
{ "member": "c3f1…", "name": "Dave", "since": 11 }
```

`member` is a random ID the launcher makes once per run, so two launchers with the same name stay separate. `since` is `0` or absent for an immediate answer. The response:

```json
{
  "id": "9a0e…",
  "name": "Dave's lobby",
  "revision": 12,
  "presence": true,
  "online": ["Dave", "Sam", "Paul"],
  "games": [
    {
      "id": "6f1c…",
      "title": "Sensible Soccer",
      "host": "Paul",
      "state": "configuring",
      "players": 2,
      "joined": 1,
      "created": "2026-11-21T20:16:03Z"
    }
  ]
}
```

- **`id`** is random per lobby run. It lets a launcher see that two entries are one lobby.
- **`name`** is the `--name` flag (or `LOBBY_NAME` in Docker), or empty. The launcher starts its own lobby with `--name "<Netplay name>'s lobby"`.
- **`revision`** moves whenever a listed game is created, a slot is claimed or freed, a game's state changes, a game ends or is reaped, or, with presence on, someone comes online or goes offline. With `since` the route waits until the revision passes it, or until the usual 25 s pass, exactly like `GET /game/{id}?since=`.
- **`presence` and `online`.** With `--presence` (or `PRESENCE=1`), a member counts as online while it has a poll open or one answered in the last 35 s. That's the 25 s long-poll wait plus margin. Without it, `presence` is `false`, `online` is absent, and `member` and `name` are ignored. The launcher always passes `--presence` to the lobby it runs. It's off by default for Docker, so a public lobby doesn't show strangers' names to everyone browsing it. Whoever runs it can set `PRESENCE=1`.
- **What's left out.** The listing carries no tokens, password, config or addresses. Joining still goes through `POST /game/{id}/players`, and the joiner gets those from the session as now.
- **`title`** is display-only, up to 64 bytes. It's taken from the host's loaded config name, since `__config_name` isn't a synced key. `host` is slot 0's tag.
- **`auto_start`** starts the game when it reaches `ready`, as in [Starting](#starting). `"listed"` and `"auto_start"` both default to `false` when absent, so an older launcher's `POST /game` behaves exactly as now.

Implementation notes:

- **Waking watchers.** The lobby gets its own `revision` and `changed` channel under `l.mu`, the same shape as an entry's. An entry's `changedLocked()` also bumps the lobby's when the entry is listed, so every path that already wakes session watchers wakes the browser too.
- **Presence** is a `member → {name, lastSeen, polling}` map, swept by the existing reaper loop. Members are capped at 256, with `503` past that.
- **Auto-start** is a check at the end of `reportReady`: `if e.autoStart && e.stateLocked() == StateReady { l.startLocked(e) }`.
- **The handler** copies `handleSnapshot`, including the `SetWriteDeadline` extension for long-polls.
- **No limit is needed on games.** The listing is bounded by `--max-games` (64 by default).

## Polling and unresponsive servers

**Polling.** Each server gets a long-poll on its own thread: `POST /lobby` with `since`. The API also answers a plain request immediately, so the launcher could switch to a timer later without changing the server.

- *Why:* changes, including presence, show up immediately, and an idle server costs one held connection per watching launcher, answered every 25 s. It's the same pattern and code shape as `SessionWatcher`.
- *Not a timer:* a plain request every 15–60 s is simpler to reason about behind proxies. But new games would take that long to appear, and presence would need its window raised past the interval, so people would look online for a while after leaving.
- *When:* watching starts when the Net Play tab is first shown and stops when the launcher closes. It carries on while another tab is showing, so you don't look offline while you pick a game.

**Unresponsive servers.** Each server has a state in the panel:

| State | When | What the launcher does |
|---|---|---|
| Connecting | First request in flight | Shows *connecting…* |
| Online | Last request answered | Shows the server's games and, with presence, who's online |
| Can't reach | Connect fails, times out (5 s to connect, 35 s for a long-poll as `POLL_TIMEOUT`), or HTTP 5xx | Hides its games and retries with backoff: 2 s, doubling, capped at 60 s. **Retry** retries immediately |
| Not a game list | `404` or `405` on `/lobby` (an older `fsnp-server`) or a response that isn't JSON | Shows *doesn't list games (older server?)* and stops retrying until the list or the launcher restarts |

The cap is longer than `SessionWatcher`'s 10 s. A server you're browsing is less urgent than a game you're in, and a list can hold servers that are gone for good. Once you've joined or are hosting a game, that game's `SessionWatcher` keeps its own faster retry, as now.

## Launcher changes

| Piece | Change |
|---|---|
| `LobbyClient` | `lobby(member, name, since=None)` for `POST /lobby`. `create_game` gains `listed`, `title` and `auto_start` |
| `ServerWatcher` (new, in `launcher/netplay/lobby_browser.py`) | A daemon thread per server that long-polls and posts each listing, or its state, to the UI thread with `call_after`, using the backoff above |
| `LobbyBrowser` (same file) | Owns the watchers. Adds and removes them as `netplay_servers` changes and as the local lobby starts and stops. Merges the listings into one game list, de-duplicating servers by lobby `id` |
| `Netplay` | `join_game(host, port, game_id)` is split out of `on_session_announce`, with the join, stale-generation and leave-quietly handling it has now. It's called by the IRC announcement, **Join** and **Join by ID…**. `host_game(server, players, listed)` replaces the IRC-specific parts of `command_startgame` and `command_hostgame`, reusing `create_session`, `Server(port, …, lobby=True)` and `start_hosted_server`. The tag comes from `netplay_name` instead of `self.irc.my_nick`. Messages go to the activity log |
| Local lobby | Started by the first **Host game** on **This computer** with `--presence --name …`. It's kept between games, and stopped by **Stop lobby** or on exit unless a game in it is running |
| `NetplayPanel` | Servers, Games, Host game dialog, the hosting and joined views, and the activity log, as in the wireframes. The current port and player fields go: the port moves to settings, and players moves to the Host dialog |
| Settings | New: `netplay_name`, `netplay_servers`, `netplay_public_address`, `netplay_host_port`. A `LobbyServersGroup` modelled on `ScanPathsGroup` on the Net Play page. `irc_nick` is copied to `netplay_name` on first run |
| IRC commands | `/startgame` and `/hostgame` create listed, titled games without `auto_start`, so they keep working as now until IRC is removed |

The emulator side doesn't change: FSNP v1 and the game server are untouched.

## Security

- **Listed means public to anyone who can reach the server.** Anyone who can reach the lobby can see a listed game and claim a slot in it, and with the slot comes the config and the game password. That's the point of a lobby. For a private game, untick *List this game* and share the game ID, or run a lobby whose address you don't share.
- **Unlisted games are unchanged.** A game ID is still only learned from its host, so #112's private join announcements keep their meaning while IRC lasts.
- **Browsing sends your netplay name.** Every server in your list receives your name and a per-run member ID. Servers with presence on show your name to everyone browsing them. Servers without it ignore both. A server also sees your IP address, and only servers you added are contacted. There's no default server.
- **Auto-start can't be forced by a joiner.** A game starts only when the host's own slot is ready as well, and only for the host's current config version. A player can't start a game with a config the host didn't set.
- **Names and titles come from other users.** They're length-limited by the lobby (32 and 64 bytes) and shown as plain text, never as markup.
- **Plain HTTP, as today.** The listing and presence hold nothing that isn't already sent in clear text.

## Rollout

Each step is its own commit (or PR), green on its own, and leaves netplay usable.

1. **Listing in the lobby.** `listed` and `title` on `POST /game`, `POST /lobby` with long-poll, `id` and `--name`. Go tests cover the long-poll waking on create, join, leave, state change and reaping, and unlisted games staying out of the listing.
2. **Presence in the lobby.** `--presence`, the members map, and expiry through the reaper. Go tests cover coming online, the 35 s expiry and the cap.
3. **Auto-start in the lobby.** `auto_start` on `POST /game` and the check in `reportReady`. Go tests cover starting on the last ready report, not starting while a slot is empty or stale, and manual start still working without the flag.
4. **Settings.** `netplay_name`, `netplay_servers`, the hosting address and port, and `LobbyServersGroup`.
5. **Browsing.** `ServerWatcher`, `LobbyBrowser`, and the panel's read-only Servers and Games sections, including **This computer** while a `/hostgame` lobby runs. The IRC commands create listed, titled games, so there's something to see.
6. **Join from the list.** `join_game` split out of `on_session_announce`, plus **Join**, **Join by ID…**, **Leave** and the joined view.
7. **Host from the panel.** `host_game`, the Host dialog, the local lobby lifecycle with `--presence`, the hosting view, and `auto_start` on games hosted from the panel.

After this design: **remove IRC.** Delete the IRC modules, `oyoyo`, the InspIRCd service and the IRC settings, as the rooms draft planned. *Done: the IRC panel, its command box and the server details column went too, leaving the browser as the whole Net Play tab, and the IRC settings are cleared at startup once `irc_nick` has been copied to the netplay name.*

## Alternatives considered

- **Rooms keyed by a shared secret** (the previous draft). These are good for a fixed group, but you only ever see your own group, and a room can hold just one game at a time. If private groups on a public server become a need, a room key could later act as a filter on `POST /lobby`.
- **Requiring this computer's lobby in the server list.** It's uniform, with no special entry, but it often fails on routers without NAT hairpinning and shows a stale entry whenever you're not hosting. See [This computer](#this-computer).
- **The host's launcher calls start when it sees `ready`.** This needs no server change, but it adds a round trip, it races with the host changing the config, and it fails if the host's launcher is slow. The lobby already decides `ready` under its lock, so it's the right place to start.
- **A central directory of lobbies.** One well-known service that lobbies register with, so nobody has to type addresses. It's more infrastructure than we need while the servers are ones we know. A server list can grow into this later by fetching entries from a URL.
- **LAN discovery (mDNS or broadcast).** Useful at a party, but it doesn't help over the internet, which is the case we care about.

## Decisions

Settled in review of this draft:

1. **This computer isn't in the server list.** While its lobby runs, it's watched automatically over loopback, as in [This computer](#this-computer). This holds for the first iteration.
2. **Long-poll, not a timer,** and watching carries on while other tabs are showing. See [Polling and unresponsive servers](#polling-and-unresponsive-servers).
3. **Unreachable servers back off to a 60 s cap.** They aren't marked as gone in settings, however long they've been down (see follow-ups).
4. **Presence is off by default on Docker lobbies** and is turned on with `PRESENCE=1`. A lobby the launcher runs always has it on.

## Follow-ups pending feedback

Not part of this design. Each one waits on feedback from using the first iteration:

- **Mark long-dead servers.** Flag a server in settings that has been unreachable for a long time, such as an hour, as probably gone.
- **Start countdown.** Instead of launching FS-UAE the moment the last player is ready, show *Starting in 5…* on every launcher, which anyone can cancel with **Leave**. The lobby would hold the game in a short `starting` state before routing it.
- **"Do I have this game?"** Carry the variant UUID or config hash in the listing, so that the browser can mark games you can't run before you join.
