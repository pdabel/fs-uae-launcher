from pathlib import Path

from fsbc.tests.test_layering import upward_imports

FSUI_DIR = Path(__file__).resolve().parent.parent

# fsui is the widget toolkit. The game-system layer and the applications
# are built on it and pass in what it needs.
HIGHER_PACKAGES = {"fsgs", "launcher", "workspace"}


def test_fsui_does_not_import_higher_packages():
    assert upward_imports(FSUI_DIR, HIGHER_PACKAGES) == []
