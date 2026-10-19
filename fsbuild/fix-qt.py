#!/usr/bin/env python3
import os
import shutil
import sys

# The binding fsui uses; see configure_qt_environment in fsui/qt/qt.py.
os.environ.setdefault("QT_API", "pyside6")

from qtpy.QtCore import QLibraryInfo


def main():
    # This is mainly to avoid bundling libraries that can cause issues,
    # such as GTK (and dependencies) being included if GTK platform
    # integration is included.
    print("Fixing the Qt installation before running pyinstaller")
    print("(Removing unnecessary stuff")

    def removePath(path):
        print(path)
        if os.path.exists(path):
            print("Removing", path)
            shutil.rmtree(path)

    def location(name):
        return QLibraryInfo.path(getattr(QLibraryInfo.LibraryPath, name))

    removePath(location("QmlImportsPath"))
    removePath(location("TranslationsPath"))

    pluginsPath = location("PluginsPath")
    print(pluginsPath)

    def removePlugins(type):
        pluginTypePath = os.path.join(pluginsPath, type)
        print(pluginTypePath)
        if os.path.exists(pluginTypePath):
            print("Removing", pluginTypePath)
            shutil.rmtree(pluginTypePath)

    if sys.platform == "linux":
        removePlugins("platformthemes")


if __name__ == "__main__":
    main()
