import ast
from pathlib import Path
import runpy
import subprocess
import sys
from types import SimpleNamespace
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


def test_python_literal_templates_use_f_strings():
    root = Path(__file__).resolve().parents[2]
    filenames = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=root
    ).decode().split("\0")
    legacy_calls = []
    for filename in filter(None, filenames):
        path = root / filename
        if not path.is_file():
            continue
        source = path.read_bytes()
        if path.suffix != ".py" and not source.startswith(
            (b"#!/usr/bin/env python", b"#!/usr/bin/python")
        ):
            continue
        tree = ast.parse(source, filename=filename)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "format"
                and isinstance(node.func.value, ast.Constant)
                and isinstance(node.func.value.value, str)
            ):
                legacy_calls.append(f"{filename}:{node.lineno}")
    assert not legacy_calls, "Literal .format calls: " + ", ".join(legacy_calls)


def test_translation_precedes_template_substitution():
    root = Path(__file__).resolve().parents[2]
    cases = [
        (
            "fsgs/ogd/lists.py",
            "Updating list '{0}'...",
            "Liste '{0}' aktualisieren",
            "Favorites",
            "Liste 'Favorites' aktualisieren",
        ),
        (
            "launcher/ui/download.py",
            "Download to the following directory, and then click '{0}':",
            "Cliquer sur {0}",
            "Scan Downloads",
            "Cliquer sur Scan Downloads",
        ),
        (
            "launcher/ui/statusbar/WarningsElement.py",
            "Outdated plugins: {0}",
            "Modules anciens: {0}",
            "Plugin A, Plugin B",
            "Modules anciens: Plugin A, Plugin B",
        ),
    ]
    for filename, template, translated, value, expected in cases:
        tree = ast.parse((root / filename).read_bytes())
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "format"
            and isinstance(node.func.value, ast.Call)
            and isinstance(node.func.value.func, ast.Name)
            and node.func.value.func.id == "gettext"
            and node.func.value.args
            and isinstance(node.func.value.args[0], ast.Constant)
            and node.func.value.args[0].value == template
        ]
        assert len(calls) == 1, filename
        call = calls[0]
        call.args = [ast.Constant(value=value)]
        expression = ast.fix_missing_locations(ast.Expression(body=call))
        translations = {template: translated}
        actual = eval(
            compile(expression, filename, "eval"),
            {"gettext": translations.__getitem__},
        )
        assert actual == expected, filename


def test_irc_f_string_command_output():
    root = Path(__file__).resolve().parents[2]
    filename = "launcher/netplay/irc.py"
    tree = ast.parse((root / filename).read_bytes())
    methods = {
        node.name: node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    cases = [
        ("command_whois", ["Alice", "Bob"], "whois Alice Bob"),
        ("command_away", ["out", "today"], "away out today"),
        ("command_away", [], "away"),
        ("command_mode", ["#test", "+o", "Alice"], "mode #test +o Alice"),
    ]
    for name, arguments, expected in cases:
        namespace = {}
        module = ast.Module(body=[methods[name]], type_ignores=[])
        exec(compile(module, filename, "exec"), namespace)
        sent = []
        instance = SimpleNamespace(client=SimpleNamespace(send=sent.append))
        namespace[name](instance, arguments)
        assert sent == [expected], name


def test_whdload_logging_uses_lazy_arguments():
    import logging

    root = Path(__file__).resolve().parents[2]
    filename = "fsgs/amiga/whdload.py"
    tree = ast.parse((root / filename).read_bytes())
    call = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "debug"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "[WHDLOAD] %s => %s"
    )
    captured = []
    namespace = {
        "archive_name": "Game.lha",
        "args": ["CUSTOM1=1", "PRELOAD"],
        "logging": SimpleNamespace(debug=lambda *args: captured.append(args)),
    }
    eval(compile(ast.Expression(body=call), filename, "eval"), namespace)
    assert captured == [
        ("[WHDLOAD] %s => %s", "Game.lha", "CUSTOM1=1 PRELOAD")
    ]
    record = logging.LogRecord(
        "test", logging.DEBUG, filename, 0, captured[0][0], captured[0][1:], None
    )
    assert record.getMessage() == "[WHDLOAD] Game.lha => CUSTOM1=1 PRELOAD"


def test_bootstrap_f_string_templates():
    import builtins
    import io

    import config

    root = Path(__file__).resolve().parents[2]
    outputs = {}
    real_open = builtins.open

    class CapturedOutput(io.StringIO):
        def close(self):
            pass

    def capture(filename, mode="r", *arguments, **keywords):
        if filename in ("setup.py", "Makefile") and mode == "w":
            outputs[filename] = CapturedOutput()
            return outputs[filename]
        if filename == "config.py":
            filename = root / filename
        return real_open(filename, mode, *arguments, **keywords)

    with patch("builtins.open", capture):
        with patch("os.listdir", return_value=["fr.po", "de.po"]):
            runpy.run_path(str(root / "bootstrap"))

    setup = outputs["setup.py"].getvalue()
    makefile = outputs["Makefile"].getvalue()
    compile(setup, "generated setup.py", "exec")
    assert f"You should not install {config.title} to the default" in setup
    for package in config.packages:
        assert f"res_dirs.append({package + '/res'!r})\n" in setup
    assert f"dist_name = {config.tar_name}-$(version)" in makefile
    catalogs = (
        f"\tshare/locale/de/LC_MESSAGES/{config.tar_name}.mo \\\n"
        f"\tshare/locale/fr/LC_MESSAGES/{config.tar_name}.mo"
    )
    assert catalogs in makefile


def test_supported_packaging_uses_pyside6():
    import json
    import tomllib

    root = Path(__file__).resolve().parents[2]
    manifest = tomllib.loads((root / "Pipfile").read_text())
    locked = json.loads((root / "Pipfile.lock").read_text())
    assert {"pyside6", "qtpy", "qtawesome"} <= manifest["packages"].keys()
    assert {"pyside6", "qtpy", "qtawesome"} <= locked["default"].keys()
    assert locked["default"]["pyside6"]["version"].startswith("==6.")
    for packages in (
        manifest["packages"], manifest["dev-packages"],
        locked["default"], locked["develop"],
    ):
        assert not any(name.lower().startswith("pyqt") for name in packages)

    paths = [
        "fsbuild/build.sh", "fsbuild/bundle.sh", "fsbuild/fix-qt.py",
        "fs-uae-launcher.spec", "debian/control",
        ".github/workflows/linux.yml", ".github/workflows/macos.yml",
    ]
    for filename in paths:
        source = (root / filename).read_text().lower()
        assert "pyqt5" not in source, filename
        assert "pyqt6" not in source, filename
        assert "bundle-clean-" not in source, filename
    assert not list((root / "fsbuild").glob("bundle-clean-*.sh"))

    build = (root / "fsbuild/build.sh").read_text()
    assert "fsbuild/fix-qt.py" in build
    assert "PySide6/Qt" in build
    helper = ast.parse((root / "fsbuild/fix-qt.py").read_bytes())
    defaults = [
        node for node in ast.walk(helper)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "setdefault"
        and [argument.value for argument in node.args
             if isinstance(argument, ast.Constant)] == ["QT_API", "pyside6"]
    ]
    assert len(defaults) == 1