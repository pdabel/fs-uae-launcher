from importlib.resources import files

import launcher.version

VERSION = launcher.version.VERSION


# noinspection PyPep8Naming
def Stream(package, name):
    return files(package).joinpath(name).open("rb")
