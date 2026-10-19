from unittest.mock import Mock

import pytest

from launcher.netplay import netplay as netplay_module
from launcher.netplay.channel import Channel
from launcher.server.Server import BUILD_HINT, ServerError
from oyoyo import helpers


@pytest.mark.parametrize(
    "diagnostic",
    [
        "Could not launch netplay server '/server/fsnp-server': "
        "[Errno 13] Permission denied: '/server/fsnp-server'. "
        "Check that this is a server executable file, that you "
        "have permission to run it, and that its filesystem "
        "allows execution. "
        "To build it from this checkout: " + BUILD_HINT,
        "Could not launch netplay server: " + "\u00e9" * 1000,
    ],
    ids=["permission-denied-build-guidance", "long-utf8-diagnostic"],
)
@pytest.mark.parametrize("channel_name", ["#game", "#" + "g" * 49])
def test_hostgame_keeps_detailed_startup_error_local(
    monkeypatch, diagnostic, channel_name
):
    old_wire_line = (
        f"PRIVMSG {channel_name} :ERROR: could not start the netplay server: "
        f"{diagnostic}\r\n"
    ).encode("utf-8")
    assert len(old_wire_line) > 512
    client = Mock()
    irc = Mock(my_nick="host")
    channel = Channel(irc, channel_name)
    channel.ops.add("host")
    irc.active_channel.return_value = channel
    irc.privmsg.side_effect = lambda target, message: helpers.msg(
        client, target, message
    )
    netplay = netplay_module.Netplay.__new__(netplay_module.Netplay)
    netplay.irc = irc
    netplay.parent = Mock()
    netplay.game_window = None
    monkeypatch.setattr(netplay, "require_game_channel", lambda channel: True)
    monkeypatch.setattr(
        netplay,
        "parse_server_args",
        lambda args, port: ("localhost", port, 2, ""),
    )
    server = Mock()
    server.start.side_effect = ServerError(diagnostic)
    monkeypatch.setattr(netplay_module, "Server", Mock(return_value=server))
    set_config = Mock()
    monkeypatch.setattr(
        netplay_module.LauncherConfig, "set_multiple", set_config
    )

    netplay.command_hostgame(["localhost"])

    client.send.assert_called_once()
    wire_line = (" ".join(client.send.call_args.args) + "\r\n").encode("utf-8")
    assert len(wire_line) <= 512
    assert diagnostic not in wire_line.decode("utf-8")
    assert any(
        line == f"ERROR: could not start the netplay server: {diagnostic}\n"
        for line in channel.lines
    )
    assert b"could not start the netplay server" in wire_line
    netplay.parent.create_server_view.assert_not_called()
    set_config.assert_not_called()
    assert netplay.game_window is None
