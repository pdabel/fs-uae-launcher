"""Lobby addresses, and the list of lobby servers the Net Play tab watches.

The list is the netplay_servers setting, ";"-separated like search_path,
each entry host or host:port. See "Servers" in
docs/netplay-rooms-design.md.

This module has no launcher dependencies beyond reading and writing that
setting through the functions passed in, so it can be tested on its own.
"""

# The lobby's port, for /startgame and /hostgame alike, so a host forwards
# the same single port however they host.
HOST_PORT = 25101

SEPARATOR = ";"


def format_lobby(host, port):
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"{host}:{port}"


def parse_lobby(text, default_port=HOST_PORT):
    """host[:port] or [v6]:port -> (host, port)."""
    if text.startswith("["):
        host, _, rest = text[1:].partition("]")
        port = rest[1:] if rest.startswith(":") else ""
    elif text.count(":") == 1:
        host, port = text.split(":")
    else:
        host, port = text, ""
    return host, int(port) if port else default_port


def normalize_server(text):
    """A server list entry as stored: lowercase host, default port left off.

    Raises ValueError, with a message for the user, for anything that
    isn't host or host:port.
    """
    text = text.strip()
    try:
        host, port = parse_lobby(text)
    except ValueError:
        raise ValueError(f"{text!r} is not host or host:port") from None
    host = host.lower()
    if not host or any(c.isspace() or c in "/;[]" for c in host):
        raise ValueError(f"{text!r} is not host or host:port")
    if not 1 <= port <= 65535:
        raise ValueError(f"port {port} is not between 1 and 65535")
    if port == HOST_PORT:
        return host
    return format_lobby(host, port)


def split_servers(value):
    """The setting's entries, normalised, without blanks, bad entries or
    duplicates."""
    servers = []
    for entry in value.split(SEPARATOR):
        try:
            entry = normalize_server(entry)
        except ValueError:
            continue
        if entry not in servers:
            servers.append(entry)
    return servers


def add_server(value, text):
    """The setting with text added; ValueError if it's invalid or there."""
    entry = normalize_server(text)
    servers = split_servers(value)
    if entry in servers:
        raise ValueError(f"{entry} is already in the list")
    return SEPARATOR.join(servers + [entry])


def remove_server(value, entry):
    """The setting without entry."""
    return SEPARATOR.join(s for s in split_servers(value) if s != entry)
