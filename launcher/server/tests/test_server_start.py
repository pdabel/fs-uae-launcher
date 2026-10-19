import errno
import importlib
import os
from unittest.mock import Mock

import pytest

from fsgs.plugins import pluginexecutablefinder as finder

server_module = importlib.import_module("launcher.server.Server")


@pytest.mark.parametrize("kind", ["missing", "directory", "file", "symlink"])
def test_check_executable_requires_file(tmp_path, kind):
    candidate = tmp_path / "fsnp-server"
    if kind == "directory":
        candidate.mkdir()
    elif kind == "file":
        candidate.write_bytes(b"server")
    elif kind == "symlink":
        target = tmp_path / "server"
        target.write_bytes(b"server")
        candidate.symlink_to(target)
    assert finder.check_executable(str(candidate)) == (
        kind in ("file", "symlink")
    )


def test_unbuilt_checkout_does_not_launch_source_directory(
    tmp_path, monkeypatch
):
    (tmp_path / "fsnp-server").mkdir()
    monkeypatch.setattr(server_module.fsboot, "development", lambda: True)
    monkeypatch.setattr(
        server_module.fsboot, "executable_dir", lambda: str(tmp_path)
    )
    monkeypatch.setattr(
        finder, "find_executable_in_development_project_dir", lambda name: None
    )
    monkeypatch.setattr(
        finder, "find_executable_in_plugins_dir", lambda name: None
    )
    monkeypatch.setattr(
        finder, "find_executable_in_side_by_side_plugin", lambda name: None
    )
    popen = Mock()
    monkeypatch.setattr(server_module.subprocess, "Popen", popen)

    with pytest.raises(server_module.ServerError) as caught:
        server_module.Server(25101, 2, "").start()

    assert "Could not find the fsnp-server executable" in str(caught.value)
    assert server_module.BUILD_HINT in str(caught.value)
    assert "sudo apt install golang-go" in str(caught.value)
    assert "on macOS with Homebrew: brew install go" in str(caught.value)
    assert "https://go.dev/dl/" in str(caught.value)
    popen.assert_not_called()


def test_development_binary_is_found(tmp_path, monkeypatch):
    directory = tmp_path / "fsnp-server"
    directory.mkdir()
    binary = directory / finder.get_exe_name("fsnp-server")
    binary.write_bytes(b"server")
    monkeypatch.setattr(server_module.fsboot, "development", lambda: True)
    monkeypatch.setattr(
        server_module.fsboot, "executable_dir", lambda: str(tmp_path)
    )
    assert server_module.find_server_executable() == str(binary)


def test_missing_packaged_server_has_install_guidance(monkeypatch):
    monkeypatch.setattr(server_module, "find_server_executable", lambda: None)
    monkeypatch.setattr(server_module.fsboot, "development", lambda: False)

    with pytest.raises(server_module.ServerError, match="Reinstall"):
        server_module.Server(25101, 2, "").start()


@pytest.mark.parametrize("development", [False, True])
@pytest.mark.parametrize(
    "error_number, guidance",
    [
        (errno.EACCES, "permission to run it"),
        (errno.EPERM, "permission to run it"),
        (errno.ENOENT, "executable or its required loader is missing"),
        (errno.ENOEXEC, "CPU architecture"),
        (errno.EMFILE, "operating-system error above"),
    ],
)
def test_launch_error_is_actionable(
    monkeypatch, development, error_number, guidance
):
    executable = "/server/fsnp-server"
    error = OSError(error_number, "launch failed", executable)
    monkeypatch.setattr(
        server_module, "find_server_executable", lambda: executable
    )
    monkeypatch.setattr(server_module, "log_file_path", lambda: None)
    monkeypatch.setattr(
        server_module.fsboot, "development", lambda: development
    )
    monkeypatch.setattr(
        server_module.subprocess, "Popen", Mock(side_effect=error)
    )
    register = Mock()
    monkeypatch.setattr(server_module.atexit, "register", register)
    server = server_module.Server(25101, 2, "")

    with pytest.raises(server_module.ServerError) as caught:
        server.start()

    message = str(caught.value)
    assert executable in message
    assert str(error) in message
    assert guidance in message
    assert (server_module.BUILD_HINT in message) == development
    assert caught.value.__cause__ is error
    assert server.process is None
    register.assert_not_called()


@pytest.mark.skipif(os.name == "nt", reason="POSIX execute permissions")
def test_real_permission_denied_is_handled(tmp_path, monkeypatch):
    binary = tmp_path / "fsnp-server"
    binary.write_bytes(b"not executable")
    binary.chmod(0o600)
    monkeypatch.setattr(
        server_module, "find_server_executable", lambda: str(binary)
    )
    monkeypatch.setattr(server_module, "log_file_path", lambda: None)
    monkeypatch.setattr(server_module.fsboot, "development", lambda: False)
    server = server_module.Server(25101, 2, "")

    with pytest.raises(
        server_module.ServerError, match="permission to run it"
    ) as caught:
        server.start()

    assert isinstance(caught.value.__cause__, PermissionError)
    assert server.process is None


@pytest.mark.parametrize(
    "reason, exception",
    [
        ("address_in_use", server_module.PortInUseError),
        ("other", server_module.ServerError),
    ],
)
def test_server_reported_error_is_preserved(monkeypatch, reason, exception):
    monkeypatch.setattr(
        server_module, "find_server_executable", lambda: "/server/fsnp-server"
    )
    monkeypatch.setattr(server_module, "log_file_path", lambda: None)
    process = Mock()
    process.stdout.readline.return_value = (
        '{"event":"error","reason":"%s","message":"cannot listen"}\n' % reason
    ).encode("utf-8")
    process.poll.return_value = 1
    monkeypatch.setattr(
        server_module.subprocess, "Popen", Mock(return_value=process)
    )
    monkeypatch.setattr(server_module.atexit, "register", Mock())
    server = server_module.Server(25101, 2, "")

    with pytest.raises(exception, match="cannot listen") as caught:
        server.start()

    assert type(caught.value) is exception
    if reason == "address_in_use":
        assert caught.value.port == 25101
    assert server.process is None


def test_successful_launch_still_waits_for_readiness(monkeypatch):
    monkeypatch.setattr(
        server_module, "find_server_executable", lambda: "/server/fsnp-server"
    )
    monkeypatch.setattr(server_module, "log_file_path", lambda: None)
    process = Mock()
    process.stdout.readline.return_value = (
        b'{"event":"listening","port":25101}\n'
    )
    popen = Mock(return_value=process)
    monkeypatch.setattr(server_module.subprocess, "Popen", popen)
    register = Mock()
    monkeypatch.setattr(server_module.atexit, "register", register)
    server = server_module.Server(25101, 2, "")

    server.start()

    assert server.process is process
    assert server.port == 25101
    popen.assert_called_once_with(
        [
            "/server/fsnp-server",
            "--port=25101",
            "--players=2",
            "--exit-on-stdin-close",
        ],
        stdin=server_module.subprocess.PIPE,
        stdout=server_module.subprocess.PIPE,
        close_fds=True,
    )
    register.assert_called_once_with(server.stop)
    process.stdout.readline.assert_called_once_with()
