import threading

from launcher.launcher_config import LauncherConfig
from launcher.netplay import connection_tester
from launcher.netplay.connection_tester import ConnectionTester
from launcher.netplay.netplay import Netplay


def test_connection_attempt_has_a_timeout(monkeypatch):
    calls = []

    def create_connection(address, timeout=None):
        calls.append((address, timeout))
        raise TimeoutError("timed out")

    monkeypatch.setattr(
        connection_tester.socket, "create_connection", create_connection
    )
    tester = ConnectionTester()
    try:
        host, error = tester.test_connection(("192.0.2.1", "25100"))
    finally:
        tester.stop()
    assert host == ""
    assert "timed out" in error
    assert calls == [(("192.0.2.1", 25100), connection_tester.TIMEOUT)]


def test_stopped_tester_thread_ends_without_reporting(monkeypatch):
    config = {"__netplay_addresses": "192.0.2.1", "__netplay_port": "25100"}
    monkeypatch.setattr(LauncherConfig, "get", lambda key: config[key])
    tested = threading.Event()
    reported = []

    def test_connection(self, host_info):
        tested.set()
        self.stop()
        return "", "refused"

    monkeypatch.setattr(ConnectionTester, "test_connection", test_connection)
    monkeypatch.setattr(connection_tester, "call_after", reported.append)
    tester = ConnectionTester()
    tester.on_config("__netplay_port", "25100")
    assert tested.wait(3)
    tester.thread.join(3)
    assert not tester.thread.is_alive()
    assert tester.thread.daemon
    assert reported == []


def test_disconnect_stops_the_connection_tester(monkeypatch):
    netplay = Netplay()
    monkeypatch.setattr(netplay, "start_browsing", lambda: None)
    netplay.connect()
    tester = netplay.connection_tester
    netplay.disconnect()
    assert netplay.connection_tester is None
    assert tester.stopping
