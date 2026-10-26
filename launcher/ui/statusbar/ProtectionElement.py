from fsui import Image
from ...launcher_config import LauncherConfig
from ...i18n import gettext
from .StatusElement import StatusElement


class ProtectionElement(StatusElement):
    def __init__(self, parent):
        StatusElement.__init__(self, parent)
        self.protection_icon = Image("launcher:res/16x16/lock.png")
        self.disabled_icon = Image("launcher:res/16x16/lock_open_green.png")
        self.icon = self.protection_icon

        self.na_text = " "
        self.protection = ""
        self.text = self.na_text
        self.active = False

        LauncherConfig.add_listener(self)
        self.on_config("protection", LauncherConfig.get("protection"))

    def on_destroy(self):
        LauncherConfig.remove_listener(self)

    def on_config(self, key, value):
        if key == "protection":
            print(" -- protection --", value)
            if value != self.protection:
                self.protection = value
                if not value:
                    self.icon = self.protection_icon
                    self.active = False
                    self.text = self.na_text
                elif value.lower() == "none":
                    self.icon = self.protection_icon
                    self.active = False
                    self.text = gettext("No Protection")
                elif value.lower() in ["dongle"]:
                    self.icon = self.protection_icon
                    self.active = False
                    self.text = gettext("Dongle")
                else:
                    self.icon = self.protection_icon
                    self.active = True
                    self.text = value
                self.refresh()
