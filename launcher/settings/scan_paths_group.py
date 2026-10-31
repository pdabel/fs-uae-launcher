import os

import fsui
from launcher.i18n import gettext
from launcher.launcher_settings import LauncherSettings
from launcher.ui.IconButton import IconButton
from fsbc.util import unused
from fsbc.paths import Paths
from fsgs.FSGSDirectories import FSGSDirectories


def normalized_path(path):
    return os.path.normcase(
        os.path.normpath(Paths.expand_path(path).replace("\\", "/"))
    ).replace("\\", "/")


class ScanPathsGroup(fsui.Group):
    def __init__(self, parent):
        fsui.Group.__init__(self, parent)
        self.layout = fsui.HorizontalLayout()

        self.layout2 = fsui.VerticalLayout()
        self.layout.add(self.layout2, fill=True, expand=True)

        layout3 = fsui.HorizontalLayout()
        self.layout2.add(layout3, fill=True, expand=True)

        self.list_view = fsui.ListView(self)
        self.list_view.set_min_height(130)
        self.default_icon = fsui.Image("launcher:res/folder_16.png")
        layout3.add(self.list_view, expand=True, fill=True)
        layout3.add_spacer(10)

        vlayout = fsui.VerticalLayout()
        layout3.add(vlayout, fill=True)

        add_button = IconButton(self, "add_button.png")
        add_button.set_tooltip(gettext("Add Directory to Search Path"))
        add_button.activated.connect(self.on_add_button)
        vlayout.add(add_button)
        vlayout.add_spacer(10)

        self.remove_button = IconButton(self, "remove_button.png")
        self.remove_button.set_tooltip(
            gettext("Remove Directory from Search Path")
        )
        self.remove_button.disable()
        self.remove_button.activated.connect(self.on_remove_button)
        vlayout.add(self.remove_button)

        self.repopulate_list()
        self.list_view.on_select_item = self.on_select_item
        LauncherSettings.add_listener(self)

    def on_destroy(self):
        LauncherSettings.remove_listener(self)

    def on_setting(self, key, value):
        unused(value)
        if key == "search_path":
            self.repopulate_list()

    def on_select_item(self, index):
        unused(index)
        self.remove_button.enable()

    def repopulate_list(self):
        self.list_view.clear()
        for item in self.get_search_path():
            self.list_view.add_item(item, self.default_icon)

    @classmethod
    def get_search_path(cls):
        paths = [
            normalized_path(path)
            for path in FSGSDirectories.get_default_search_path()
        ]
        search_path = LauncherSettings.get("search_path")
        for p in search_path.split(";"):
            p = p.strip()
            if not p:
                continue
            elif p[0] == "-":
                p = normalized_path(p[1:])
                if p in paths:
                    paths.remove(p)
            else:
                p = normalized_path(p)
                if p not in paths:
                    paths.append(p)
        # The Configurations dir is always scanned on startup (whenever
        # modification time has changed). If we don't include it here too
        # always, the result will be that the configs sometimes appear (on
        # startup) and disappear (on scan).
        configurations = normalized_path(
            FSGSDirectories.get_configurations_dir()
        )
        if configurations not in paths:
            paths.append(configurations)
        # Likewise, we force the Kickstarts directory to always be scanned.
        kickstarts = normalized_path(FSGSDirectories.get_kickstarts_dir())
        if kickstarts not in paths:
            paths.append(kickstarts)
        return paths

    def on_add_button(self):
        search_path = LauncherSettings.get("search_path")
        search_path = [x.strip() for x in search_path.split(";") if x.strip()]
        path = fsui.pick_directory(parent=self.get_window())
        if path:
            path = normalized_path(path)
            for i in range(len(search_path)):
                if search_path[i].startswith("-"):
                    if path == normalized_path(search_path[i][1:]):
                        search_path.remove(search_path[i])
                        break
                else:
                    if normalized_path(search_path[i]) == path:
                        # Already added.
                        break
            else:
                default_paths = [
                    normalized_path(p)
                    for p in FSGSDirectories.get_default_search_path()
                ]
                if path not in default_paths:
                    search_path.append(
                        Paths.contract_path(path, force_real_case=False)
                    )
            LauncherSettings.set("search_path", ";".join(search_path))

    def on_remove_button(self):
        path = normalized_path(
            self.list_view.get_item(self.list_view.get_index())
        )
        search_path = LauncherSettings.get("search_path")
        search_path = [x.strip() for x in search_path.split(";") if x.strip()]
        for i in range(len(search_path)):
            if search_path[i].startswith("-"):
                if path == normalized_path(search_path[i][1:]):
                    # Already removed.
                    break
            else:
                if normalized_path(search_path[i]) == path:
                    search_path.remove(search_path[i])
                    break
        default_paths = [
            normalized_path(p)
            for p in FSGSDirectories.get_default_search_path()
        ]
        if path in default_paths:
            stored = (
                "$BASE/"
                if path == normalized_path(FSGSDirectories.get_base_dir())
                else Paths.contract_path(path, force_real_case=False)
            )
            search_path.append("-" + stored)
        LauncherSettings.set("search_path", ";".join(search_path))
