import atexit
import json
import queue
import subprocess
import threading
import traceback
from os import path

import fsboot
from fsgs.plugins.pluginexecutablefinder import (
    PluginExecutableFinder,
    get_exe_name,
)

# Name of the netplay server executable. The plugin directory it is packaged
# in is defined by known_executables in pluginexecutablefinder.py.
EXECUTABLE_NAME = "fsnp-server"

# How long to wait for the server to report that it is listening before
# giving up on it.
READY_TIMEOUT = 10.0

# How long to wait for the server to exit on its own after being asked to
# stop, before killing it.
STOP_TIMEOUT = 2.0

# Log file the server appends to, in the launcher's usual logs directory.
# This is not just a convenience: fsbc.logging replaces sys.stdout/stderr
# with NullOutput in frozen builds, and a packaged launcher started without
# a console has no usable stderr for the child to inherit, so the log file
# is the only place server output reliably ends up.
LOG_NAME = "fsnp-server.log.txt"


class ServerError(Exception):
    """The netplay server could not be found, started, or did not come up."""


def log_file_path():
    """Path the server should append its log to, or None if unavailable."""
    try:
        from fsgs.FSGSDirectories import FSGSDirectories

        return path.join(FSGSDirectories.get_logs_dir(), LOG_NAME)
    except Exception:
        traceback.print_exc()
        return None


def find_server_executable():
    """Locate the fsnp-server binary.

    Uses the same PluginExecutableFinder as every emulator driver, so
    packaged builds find it under System/FS-UAE-Netplay-Server/<OS>/<Arch>/
    with the .exe suffix on Windows.

    Development mode needs one extra check first: the finder's dev-mode
    branch looks for a *sibling* project directory, which is how fs-uae and
    the other plugins are checked out, but the Go module for this server is
    nested inside this repository (fsnp-server/) instead. See "Locating the
    binary" in docs/netplay-go-server-design.md.
    """
    if fsboot.development():
        exe_file = path.join(
            fsboot.executable_dir(),
            "fsnp-server",
            get_exe_name(EXECUTABLE_NAME),
        )
        if path.isfile(exe_file):
            return path.normpath(exe_file)
        print("- Netplay server is not built at", exe_file)
    return PluginExecutableFinder().find_executable(EXECUTABLE_NAME)


class Server:
    def __init__(self, port, players, password):
        self.port = port
        self.players = players
        self.password = password
        self.process = None

    def start(self):
        """Start the netplay server and wait until it is listening.

        Raises ServerError if the executable cannot be found, if it exits
        immediately (a port already in use, say), or if it does not report
        that it is listening within READY_TIMEOUT.
        """
        exe_file = find_server_executable()
        if exe_file is None:
            raise ServerError(
                "Could not find the {0} executable".format(EXECUTABLE_NAME)
            )
        args = [
            exe_file,
            "--port={0}".format(self.port),
            "--players={0}".format(self.players),
            # Stop the server if the launcher goes away without closing it.
            "--exit-on-stdin-close",
        ]
        if self.password:
            args.append("--password={0}".format(self.password))
        log_file = log_file_path()
        if log_file:
            args.append("--log-file={0}".format(log_file))
            print("Netplay server log:", log_file)
        print("Starting netplay server, args =", args)
        # The server logs to stderr, which is inherited so its output shows
        # up alongside the launcher's own. Only the readiness line goes to
        # stdout, so this pipe cannot fill up and block the server.
        self.process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            close_fds=True,
        )
        atexit.register(self.stop)
        self.__wait_until_listening()

    def __wait_until_listening(self):
        line = self.__read_ready_line()
        try:
            event = json.loads(line)
        except ValueError:
            self.stop()
            raise ServerError(
                "Unexpected output from netplay server: {0!r}".format(line)
            )
        if event.get("event") != "listening":
            self.stop()
            raise ServerError(
                "Netplay server did not start listening: {0!r}".format(line)
            )
        # With an explicit port the server either binds it or fails, so this
        # is a consistency check rather than a lookup. It does matter if
        # --port=0 is ever used, where the server picks the port itself.
        port = event.get("port")
        if port and int(port) != int(self.port):
            print("Netplay server is listening on port", port)
            self.port = int(port)
        print("Netplay server is listening on port", self.port)

    def __read_ready_line(self):
        """Read the server's one-line readiness event from stdout.

        Reads in a thread so a server that comes up but never prints cannot
        block the caller (the UI thread) indefinitely.
        """
        result = queue.Queue(maxsize=1)

        def read():
            try:
                result.put(self.process.stdout.readline())
            except Exception as e:
                result.put(e)

        thread = threading.Thread(
            target=read, name="fsnp-server-ready", daemon=True
        )
        thread.start()
        try:
            line = result.get(timeout=READY_TIMEOUT)
        except queue.Empty:
            self.stop()
            raise ServerError(
                "Netplay server did not report that it was listening "
                "within {0:g} seconds".format(READY_TIMEOUT)
            )
        if isinstance(line, Exception):
            self.stop()
            raise ServerError(
                "Could not read from netplay server: {0}".format(line)
            )
        if not line:
            # EOF on stdout: the server exited instead of starting up. Its
            # own error message has already gone to stderr.
            returncode = self.process.wait(timeout=STOP_TIMEOUT)
            self.process = None
            raise ServerError(
                "Netplay server exited with code {0}".format(returncode)
            )
        return line.decode("UTF-8", "replace").strip()

    def stop(self):
        """Ask the server to stop, and wait briefly for it to exit."""
        process = self.process
        if process is None:
            return
        self.process = None
        if process.poll() is not None:
            return
        print("Server.stop")
        try:
            # Closing stdin makes the server cancel its context: it sends
            # ERROR_GAME_STOPPED to any connected players, then exits.
            if process.stdin is not None:
                process.stdin.close()
        except Exception:
            traceback.print_exc()
        try:
            process.wait(timeout=STOP_TIMEOUT)
            return
        except subprocess.TimeoutExpired:
            print("Netplay server did not exit on its own, killing it")
        except Exception:
            traceback.print_exc()
        try:
            process.kill()
        except Exception:
            traceback.print_exc()

    def kill(self):
        """Deprecated alias for stop(), which shuts the server down cleanly."""
        self.stop()
