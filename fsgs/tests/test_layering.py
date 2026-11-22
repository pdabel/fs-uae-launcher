from pathlib import Path

from fsbc.tests.test_layering import upward_imports

FSGS_DIR = Path(__file__).resolve().parent.parent

# The widget toolkit and the applications are built on fsgs and pass in
# what it needs. fsgs reads screen geometry from Qt itself, not from fsui.
HIGHER_PACKAGES = {"fsui", "launcher", "workspace"}


def test_fsgs_does_not_import_higher_packages():
    assert upward_imports(FSGS_DIR, HIGHER_PACKAGES) == []
