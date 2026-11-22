import subprocess
import sys

import pytest

import fsbuild


def test_run_preserves_arguments_and_utf8():
    value = 'spaces "quotes" $HOME; * caf\u00e9'
    assert (
        fsbuild.run(
            [sys.executable, "-c", "import sys; print(sys.argv[1])", value]
        )
        == value + "\n"
    )


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
