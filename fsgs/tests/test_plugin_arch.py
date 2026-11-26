import pytest

from fsgs.plugins import pluginexecutablefinder, pluginmanager


@pytest.mark.parametrize(
    ("machine", "expected"),
    [
        ("x86_64", "x86-64"),
        ("AMD64", "x86-64"),
        ("arm64", "ARM64"),
        ("aarch64", "ARM64"),
        ("mips", "Unknown"),
    ],
)
def test_plugin_arch_names(monkeypatch, machine, expected):
    monkeypatch.setattr(
        pluginexecutablefinder.platform, "machine", lambda: machine
    )
    if expected == "x86-64":
        monkeypatch.setattr(
            pluginexecutablefinder.platform,
            "architecture",
            lambda: ("64bit", ""),
        )

    assert pluginexecutablefinder.arch_name() == expected

    assert pluginmanager.Plugin.arch_name(pretty=True) == expected
    normal_expected = "unknown" if expected == "Unknown" else expected
    assert pluginmanager.Plugin.arch_name(pretty=False) == normal_expected
