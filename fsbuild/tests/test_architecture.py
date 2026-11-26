import pytest

import fsbuild


@pytest.mark.parametrize(
    ("machine", "expected"),
    [
        ("x86_64", "x86-64"),
        ("AMD64", "x86-64"),
        ("arm64", "ARM64"),
        ("aarch64", "ARM64"),
    ],
)
def test_get_architecture(monkeypatch, machine, expected):
    monkeypatch.setattr(fsbuild.platform, "machine", lambda: machine)

    assert fsbuild.getArchitecture() == expected


def test_get_architecture_rejects_unsupported_machine(monkeypatch):
    monkeypatch.setattr(fsbuild.platform, "machine", lambda: "mips")

    with pytest.raises(RuntimeError, match="Unsupported architecture: mips"):
        fsbuild.getArchitecture()
