"""Fixtures for tests that run a real fsnp-server."""

import json
import os
import shutil
import subprocess

import pytest

REPO = os.path.join(os.path.dirname(__file__), *[os.pardir] * 3)
MODULE = os.path.join(REPO, "fsnp-server")


@pytest.fixture(scope="session")
def fsnp_server_binary(tmp_path_factory):
    """Path to an fsnp-server binary, or skip the test.

    FSNP_SERVER names one. Otherwise it is built with a local Go
    toolchain — fresh, since a binary left over from an older make may
    predate the API under test — falling back to fsnp-server/fsnp-server
    (what `make -C fsnp-server` builds).
    """
    if os.environ.get("FSNP_SERVER"):
        return os.environ["FSNP_SERVER"]
    go = shutil.which("go")
    if go is not None:
        out = str(tmp_path_factory.mktemp("fsnp") / "fsnp-server")
        subprocess.run(
            [go, "build", "-o", out, "./cmd/fsnp-server"],
            cwd=MODULE,
            check=True,
            timeout=300,
        )
        return out
    built = os.path.join(MODULE, "fsnp-server")
    if os.path.isfile(built):
        return built
    pytest.skip("no fsnp-server binary and no Go toolchain to build one")


@pytest.fixture(scope="session")
def lobby_port(fsnp_server_binary):
    """Port of an fsnp-server --lobby on 127.0.0.1, for the session."""
    proc = subprocess.Popen(
        [fsnp_server_binary, "--lobby", "--host", "127.0.0.1", "--port", "0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        ready = json.loads(proc.stdout.readline())
        assert ready["event"] == "listening", ready
        yield ready["port"]
    finally:
        proc.terminate()
        proc.wait(timeout=10)
