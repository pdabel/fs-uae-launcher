import fsgs
from launcher.settings.maintenance_settings_page import DefragmentDatabasesTask

import fsui
import qtawesome as qta
from fsbc.application import app
from fsui.qt import QPalette
from fsui.extra.taskdialog import TaskDialog
from launcher.option import Option
from launcher.res import gettext
from launcher.settings.settings_page import SettingsPage


class LauncherSettingsPage(SettingsPage):
    def __init__(self, parent):
        super().__init__(parent)
        icon = fsui.Icon("fs-uae-launcher", "pkg:launcher")
        self.add_header(icon, f"{fsgs.product} Launcher")

        theme_group = self.add_option(Option.LAUNCHER_THEME)
        self.theme_choice = theme_group.widget
        self.restart_button = fsui.Button(self, gettext("Restart Launcher"))
        palette = self.restart_button.widget().palette()
        self.restart_button.widget().setIcon(qta.icon(
            "fa5s.redo", color=palette.color(QPalette.ButtonText).name()
        ))
        self.restart_button.set_tooltip(gettext("Restart to apply the selected theme and font"))
        self.restart_button.activated.connect(self.on_restart_button)
        self.add_option(Option.LAUNCHER_FONT_SIZE)
        self.layout.add(self.restart_button, margin_bottom=10)

        self.add_option(Option.LAUNCHER_CLOSE_BUTTONS)

        self.add_section(gettext("Maintenance"))
        label = fsui.MultiLineLabel(
            self,
            gettext(
                "Defragmenting the databases will improve performance "
                "by ensuring that tables and indices are stored contiguously "
                "on disk. It will also reclaim some storage space."
            ),
            640,
        )
        self.layout.add(label, fill=True, margin_top=20)
        button = fsui.Button(self, gettext("Defragment Databases"))
        button.activated.connect(self.on_defragment_button)
        self.layout.add(button, margin_top=20)

    def on_restart_button(self):
        from fsui.qt import QMessageBox
        from fsui.qt.helpers import QParent

        answer = QMessageBox.question(
            QParent(self),
            gettext("Restart Launcher"),
            gettext(
                "Restart the launcher to apply your settings?\n\n"
                "Active netplay sessions and hosted servers will stop. "
                "Unsaved configuration changes may be lost."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            app.request_restart()
        except OSError as error:
            fsui.show_error(str(error), gettext("Unable to save settings"))

    def on_defragment_button(self):
        TaskDialog(self.get_window(), DefragmentDatabasesTask()).show()
