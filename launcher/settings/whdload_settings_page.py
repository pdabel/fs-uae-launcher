import fsui
from launcher.i18n import gettext
from launcher.settings.settings_page import SettingsPage


class WHDLoadSettingsPage(SettingsPage):
    def __init__(self, parent):
        super().__init__(parent)
        icon = fsui.Icon("settings", "pkg:workspace")
        title = gettext("WHDLoad")
        subtitle = gettext("Options for WHDLoad support in FS-UAE Launcher")
        self.add_header(icon, title, subtitle)

        label = fsui.MultiLineLabel(
            self,
            gettext(
                "The following options only apply when you use the automatic "
                "WHDLoad support in FS-UAE Launcher, for example in relation with "
                "the online game database."
            ),
            640,
        )
        self.layout.add(label, fill=True, margin_top=0)

        self.add_option("whdload_preload")
        self.add_option("whdload_splash_delay")
        self.add_option("whdload_quit_key")
