import fsui
from fsgs.option import Option
from launcher.res import gettext
from launcher.settings.settings_page import SettingsPage
from fsbc.system import linux


class FSUAESettingsPage(SettingsPage):
    def __init__(self, parent):
        super().__init__(parent)
        icon = fsui.Icon("fs-uae", "pkg:launcher")
        self.add_header(icon, "FS-UAE")

        if linux:
            from launcher.settings.cpu_performance_group import CPUPerformanceGroup

            self.add_option(Option.GAME_MODE)
            self.add_option(Option.GOVERNOR_WARNING)
            self.cpu_performance_group = CPUPerformanceGroup(self)
            self.layout.add(self.cpu_performance_group, fill=True, margin_top=10)

        label = fsui.MultiLineLabel(
            self,
            gettext(
                "The following options may affect performance, "
                "so only enable them when needed for testing or "
                "debugging purposes."
            ),
            640,
        )
        self.layout.add(label, fill=True, margin_top=20)

        self.add_option(Option.LOG_AUTOSCALE)
        self.add_option(Option.LOG_INPUT)
