import ast
from pathlib import Path

FSBC_DIR = Path(__file__).resolve().parent.parent

# fsbc is the framework base. The packages built on it pass in what it
# needs (version, logs directory) instead of being imported from here.
HIGHER_PACKAGES = {"fsgs", "fsui", "launcher", "workspace"}


def imported_packages(path):
    tree = ast.parse(path.read_text(encoding="UTF-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            yield node.lineno, node.module.split(".")[0]


def upward_imports(package_dir, higher_packages):
    """Imports of higher_packages anywhere in package_dir, tests aside."""
    found = []
    for path in sorted(package_dir.rglob("*.py")):
        if "tests" in path.relative_to(package_dir).parts:
            continue
        for lineno, package in imported_packages(path):
            if package in higher_packages:
                name = path.relative_to(package_dir.parent)
                found.append(f"{name}:{lineno} imports {package}")
    return found


def test_fsbc_does_not_import_higher_packages():
    assert upward_imports(FSBC_DIR, HIGHER_PACKAGES) == []
