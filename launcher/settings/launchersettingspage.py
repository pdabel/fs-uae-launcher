import os

import fsboot
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

        self.add_section(gettext("Data Location"))
        self.portable_checkbox = fsui.CheckBox(
            self, gettext("Portable mode"), check=fsboot.is_portable()
        )
        self.portable_checkbox.changed.connect(self.on_portable_changed)
        self.layout.add(self.portable_checkbox, margin_bottom=10)
        self.layout.add(
            fsui.MultiLineLabel(self, fsboot.base_dir(), 640), fill=True
        )
        self.portable_folder_button = fsui.Button(self, gettext("Choose Data Folder..."))
        palette = self.portable_folder_button.widget().palette()
        self.portable_folder_button.widget().setIcon(qta.icon(
            "fa5s.folder-open", color=palette.color(QPalette.ButtonText).name()
        ))
        self.portable_folder_button.enable(fsboot.is_portable())
        self.portable_folder_button.activated.connect(self.on_portable_folder)
        self.layout.add(self.portable_folder_button, margin_top=10)

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

    def reset_portable_checkbox(self):
        self.portable_checkbox.blockSignals(True)
        self.portable_checkbox.check(fsboot.is_portable())
        self.portable_checkbox.blockSignals(False)

    def on_portable_changed(self):
        enabled = self.portable_checkbox.is_checked()
        self.reset_portable_checkbox()
        self.change_portable_mode(enabled)

    def on_portable_folder(self):
        self.change_portable_mode(True)

    def change_portable_mode(self, enabled):
        from fsui.qt import QMessageBox
        from fsui.qt.helpers import QParent
        from launcher.portable import PortableModeChange
        from launcher.scanner import Scanner

        if Scanner.running:
            fsui.show_error(
                gettext("Wait for the database scan to finish before changing portable mode."),
                gettext("Portable Mode"),
            )
            return
        destination = fsui.pick_directory(parent=self.get_window())
        if not destination:
            return
        override = os.environ.get("FS_UAE_BASE_DIR")
        if not enabled and override and os.path.realpath(override) != os.path.realpath(destination):
            fsui.show_error(
                gettext("This launch uses FS_UAE_BASE_DIR, which overrides the normal data folder. Choose that folder or launch without this override."),
                gettext("Unable to change portable mode"),
            )
            return
        marker_root = fsboot.portable_dir() or fsboot.executable_dir()
        change = PortableModeChange(
            fsboot.base_dir(), destination,
            os.path.join(marker_root, "Portable.ini"), enabled,
            os.path.join(fsboot.app_config_dir("fs-uae-launcher"), "base-dir"),
        )
        try:
            change.validate()
            title = gettext("Enable Portable Mode") if enabled else gettext("Disable Portable Mode")
            answer = QMessageBox.question(
                QParent(self), title,
                gettext(
                    "Copy launcher data to this folder and restart?\n\n{folder}\n\n"
                    "Original files will be kept. Files outside the current data "
                    "folder will stay in their current locations.\n\n"
                    "Active netplay sessions and hosted servers will stop. "
                    "Unsaved configuration changes may be lost."
                ).format(folder=destination),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer == QMessageBox.Yes:
                app.request_restart(portable_change=change)
        except OSError as error:
            fsui.show_error(str(error), gettext("Unable to change portable mode"))
