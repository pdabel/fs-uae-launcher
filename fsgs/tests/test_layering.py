from pathlib import Path

from fsbc.tests.test_layering import upward_imports

FSGS_DIR = Path(__file__).resolve().parent.parent

# The launcher and the workspace tools are built on fsgs and pass in what
# it needs. (fsgs and fsui still import each other.)
APPLICATIONS = {"launcher", "workspace"}


def test_fsgs_does_not_import_the_applications():
    assert upward_imports(FSGS_DIR, APPLICATIONS) == []
