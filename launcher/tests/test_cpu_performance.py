import pytest

from launcher.cpu_performance import (
    CpuPolicy,
    governor_commands,
    read_policies,
)


def policy(name="policy0", governor="powersave", cpus=(0, 1)):
    return CpuPolicy(
        name, governor, ("powersave", "performance", "schedutil"), cpus
    )


@pytest.fixture
def installed_tools(monkeypatch):
    monkeypatch.setattr(
        "launcher.cpu_performance.shutil.which",
        lambda name: "/usr/bin/" + name,
    )


def test_read_policy_values_without_changing_system(tmp_path):
    root = tmp_path / "policy0"
    root.mkdir()
    (root / "scaling_governor").write_text("powersave\n")
    (root / "scaling_available_governors").write_text(
        "powersave performance\n"
    )
    (root / "related_cpus").write_text("0 1\n")
    assert read_policies(tmp_path) == (
        CpuPolicy(
            "policy0", "powersave", ("powersave", "performance"), (0, 1)
        ),
    )
    assert (root / "scaling_governor").read_text() == "powersave\n"
    assert read_policies(tmp_path / "missing") == ()


def test_performance_uses_fixed_privileged_utility_without_shell(
    installed_tools,
):
    commands = governor_commands((policy(), policy("policy2", cpus=(2, 3))))
    assert commands == [
        [
            "/usr/bin/pkexec",
            "--disable-internal-agent",
            "/usr/bin/cpupower",
            "--cpu",
            "0,1,2,3",
            "frequency-set",
            "--governor",
            "performance",
        ]
    ]


def test_restore_preserves_different_original_governors(installed_tools):
    previous = (policy(), policy("policy2", "schedutil", (2, 3)))
    current = (
        policy(governor="performance"),
        policy("policy2", "performance", (2, 3)),
    )
    commands = governor_commands(current, previous)
    assert [command[-1] for command in commands] == ["powersave", "schedutil"]
    assert [command[4] for command in commands] == ["0,1", "2,3"]


def test_already_selected_governor_needs_no_privileged_command(
    installed_tools,
):
    current = (policy(governor="performance"),)
    assert governor_commands(current) == []
    assert governor_commands(current, current) == []


def test_restore_rejects_changed_cpu_topology(installed_tools):
    with pytest.raises(OSError, match="policies changed"):
        governor_commands((policy(cpus=(0,)),), (policy(),))


def test_unsupported_governor_does_not_run_partial_commands(installed_tools):
    unsupported = CpuPolicy("policy2", "powersave", ("powersave",), (2,))
    with pytest.raises(OSError, match="not available"):
        governor_commands((policy(), unsupported))


@pytest.mark.parametrize("missing", ["pkexec", "cpupower"])
def test_missing_tools_are_reported(monkeypatch, missing):
    monkeypatch.setattr(
        "launcher.cpu_performance.shutil.which",
        lambda name: None if name == missing else "/usr/bin/" + name,
    )
    with pytest.raises(OSError, match="require cpupower"):
        governor_commands((policy(),))


def test_missing_cpu_interface_is_reported(installed_tools):
    with pytest.raises(OSError, match="not available"):
        governor_commands(())


def test_user_folder_utilities_are_not_elevated(monkeypatch):
    monkeypatch.setattr(
        "launcher.cpu_performance.shutil.which",
        lambda name: "/home/example/bin/" + name,
    )
    with pytest.raises(OSError, match="system-installed"):
        governor_commands((policy(),))
