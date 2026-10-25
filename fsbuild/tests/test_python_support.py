from pathlib import Path
import runpy
import sys
from unittest.mock import patch


def test_bootstrap_packaging_metadata(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    import config

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.py").write_text((root / "config.py").read_text())
    (tmp_path / "po").mkdir()
    runpy.run_path(str(root / "bootstrap"), init_globals={"project": config})
    generated = (tmp_path / "setup.py").read_text()
    compile(generated, "generated setup.py", "exec")
    assert "from distutils" not in generated
    with patch.object(sys, "argv", ["setup.py", "--name"]):
        with patch("setuptools.setup") as setup:
            exec(compile(generated, "generated setup.py", "exec"), {})
    assert setup.call_args.kwargs["python_requires"] == ">=3.12"


def test_python_sources_compile_strictly():
    import subprocess
    import warnings

    root = Path(__file__).resolve().parents[2]
    filenames = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=root
    ).decode().split("\0")
    with warnings.catch_warnings():
        warnings.simplefilter("error", SyntaxWarning)
        for filename in filter(None, filenames):
            path = root / filename
            if not path.is_file():
                continue
            source = path.read_bytes()
            if path.suffix == ".py" or source.startswith(
                (b"#!/usr/bin/env python", b"#!/usr/bin/python")
            ):
                compile(source, filename, "exec")