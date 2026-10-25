import subprocess
import sys

import pytest

import fsbuild
import fstd.mypy


def test_run_preserves_arguments_and_utf8():
    value = 'spaces "quotes" $HOME; * caf\u00e9'
    assert fsbuild.run(
        [sys.executable, "-c", "import sys; print(sys.argv[1])", value]
    ) == value + "\n"


def test_run_preserves_failed_output():
    with pytest.raises(subprocess.CalledProcessError) as failure:
        fsbuild.run(
            [sys.executable, "-c", "print('output'); raise SystemExit(7)"]
        )
    assert failure.value.returncode == 7
    assert failure.value.output == b"output\n"


def test_run_missing_executable():
    with pytest.raises(FileNotFoundError):
        fsbuild.run(["/nonexistent/fs-uae-command"])


@pytest.mark.parametrize("status", [0, 7])
def test_mypy_exit_handling(monkeypatch, capsys, status):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, status, stderr=b"diagnostic\n")

    monkeypatch.setattr(fstd.mypy.subprocess, "run", run)
    if status:
        with pytest.raises(Exception, match="mypy check failed for module example"):
            fstd.mypy.check_module("example")
        assert capsys.readouterr().out == "diagnostic\n\n"
    else:
        fstd.mypy.check_module("example")
        assert capsys.readouterr().out == ""
    assert calls == [
        (["mypy", "-m", "example"], {"stderr": subprocess.PIPE, "check": False})
    ]