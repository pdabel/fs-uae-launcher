import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CpuPolicy:
    name: str
    governor: str
    available: tuple[str, ...]
    cpus: tuple[int, ...]


def read_policies(root=Path("/sys/devices/system/cpu/cpufreq")):
    policies = []
    for path in sorted(Path(root).glob("policy[0-9]*")):
        governor = (path / "scaling_governor").read_text().strip()
        available = tuple(
            (path / "scaling_available_governors").read_text().split()
        )
        cpus = tuple(
            int(cpu) for cpu in (path / "related_cpus").read_text().split()
        )
        if cpus:
            policies.append(CpuPolicy(path.name, governor, available, cpus))
    return tuple(policies)


def governor_commands(policies, previous=None):
    if not policies:
        raise OSError(
            "CPU governor controls are not available on this system."
        )
    pkexec = shutil.which("pkexec")
    cpupower = shutil.which("cpupower")
    if not pkexec or not cpupower:
        raise OSError(
            "CPU governor changes require cpupower and PolicyKit (pkexec). "
            "On Ubuntu, cpupower is supplied by the Linux tools packages."
        )
    system_paths = {
        Path("/usr/bin"),
        Path("/usr/sbin"),
        Path("/bin"),
        Path("/sbin"),
    }
    if any(
        Path(tool).parent not in system_paths for tool in (pkexec, cpupower)
    ):
        raise OSError(
            "Use the system-installed cpupower and PolicyKit utilities, not tools from a user folder."
        )
    if previous is None:
        targets = {policy.name: "performance" for policy in policies}
    else:
        if {policy.name: policy.cpus for policy in previous} != {
            policy.name: policy.cpus for policy in policies
        }:
            raise OSError(
                "CPU policies changed; the previous governors cannot be restored safely."
            )
        targets = {policy.name: policy.governor for policy in previous}
    grouped = {}
    for policy in policies:
        governor = targets[policy.name]
        if governor not in policy.available:
            raise OSError(
                f"CPU governor {governor!r} is not available for {policy.name}."
            )
        if governor != policy.governor:
            grouped.setdefault(governor, set()).update(policy.cpus)
    return [
        [
            pkexec,
            "--disable-internal-agent",
            cpupower,
            "--cpu",
            ",".join(str(cpu) for cpu in sorted(cpus)),
            "frequency-set",
            "--governor",
            governor,
        ]
        for governor, cpus in sorted(grouped.items())
    ]
