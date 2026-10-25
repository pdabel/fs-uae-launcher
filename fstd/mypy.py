import subprocess


def check_module(module_name):
    result = subprocess.run(
        ["mypy", "-m", module_name], stderr=subprocess.PIPE, check=False
    )
    if result.returncode != 0:
        print(result.stderr.decode("UTF-8"))
        raise Exception(f"mypy check failed for module {module_name}")
