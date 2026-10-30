import fsui
import qtawesome as qta
from qtpy.QtCore import QProcess, QTimer, Qt
from qtpy.QtGui import QPalette
from fsui.qt.helpers import QParent

from launcher.cpu_performance import governor_commands, read_policies
from launcher.i18n import gettext


class CPUPerformanceGroup(fsui.Group):
    def __init__(self, parent):
        super().__init__(parent)
        self.layout = fsui.VerticalLayout()
        self.previous = None
        self.busy = False
        self.restoring = False
        self.timed_out = False
        self.commands = []
        self.policies = ()
        self.status_label = fsui.MultiLineLabel(self, "", 640)
        self.status_label._widget.setTextFormat(Qt.PlainText)
        self.status_label.set_tooltip(
            gettext(
                "With Intel/AMD dynamic frequency drivers, 'powersave' does not "
                "necessarily mean the CPU is running slowly."
            )
        )
        self.layout.add(self.status_label, margin_bottom=10)
        row = fsui.HorizontalLayout()
        self.layout.add(row, fill=True)
        self.performance_button = fsui.Button(self, gettext("Set Performance"))
        self.restore_button = fsui.Button(self, gettext("Restore Previous"))
        self.refresh_button = fsui.Button(self, "")
        for control, icon in (
            (self.performance_button, "fa5s.bolt"),
            (self.restore_button, "fa5s.undo"),
            (self.refresh_button, "fa5s.sync-alt"),
        ):
            button = control.widget()
            button.setIcon(
                qta.icon(
                    icon,
                    color=button.palette().color(QPalette.ButtonText).name(),
                )
            )
        refresh = self.refresh_button.widget()
        refresh.setText("")
        refresh.setFixedSize(36, 36)
        refresh.setStyleSheet("padding: 0px;")
        refresh.setAccessibleName(gettext("Refresh CPU Governor"))
        self.refresh_button.set_min_width(36)
        self.refresh_button.set_min_height(36)
        self.refresh_button.set_tooltip(gettext("Refresh CPU Governor"))
        row.add(self.performance_button)
        row.add(self.restore_button, margin_left=10)
        row.add(self.refresh_button, margin_left=10)
        self.performance_button.activated.connect(self.on_performance)
        self.restore_button.activated.connect(self.on_restore)
        self.refresh_button.activated.connect(self.refresh)
        self.process = QProcess(QParent(self))
        self.process.finished.connect(self.on_process_finished)
        self.process.errorOccurred.connect(self.on_process_error)
        self.timeout = QTimer(QParent(self))
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self.on_timeout)
        self.refresh()

    def refresh(self):
        if self.busy:
            return
        self.refresh_button.enable()
        self.policies = ()
        try:
            self.policies = read_policies()
            if not self.policies:
                raise OSError(
                    gettext(
                        "CPU governor controls are unavailable on this system."
                    )
                )
            governors = ", ".join(
                sorted({policy.governor for policy in self.policies})
            )
            self.status_label.set_text(
                gettext("CPU governor: {governors}").format(
                    governors=governors
                )
            )
            self.performance_button.enable(
                bool(governor_commands(self.policies))
            )
            self.performance_button.set_tooltip(
                gettext(
                    "Change CPU governors system-wide; administrator approval may be required."
                )
            )
        except (OSError, ValueError) as error:
            self.performance_button.disable()
            self.performance_button.set_tooltip(str(error))
            governors = ", ".join(
                sorted({policy.governor for policy in self.policies})
            )
            status = (
                gettext("CPU governor: {governors}").format(
                    governors=governors
                )
                if governors
                else gettext("CPU governor: unavailable")
            )
            self.status_label.set_text(status + "\n" + str(error))
        self.restore_button.enable(
            self.previous is not None and bool(self.policies)
        )
        self.layout.update()

    def on_performance(self):
        self.change(False)

    def on_restore(self):
        self.change(True)

    def change(self, restore):
        from fsui.qt import QMessageBox
        from fsui.qt.helpers import QParent

        if self.busy or (restore and self.previous is None):
            return
        try:
            current = read_policies()
            commands = governor_commands(
                current, self.previous if restore else None
            )
        except (OSError, ValueError) as error:
            fsui.show_error(
                str(error), gettext("CPU Performance"), parent=self
            )
            self.refresh()
            return
        if not commands:
            if restore:
                self.previous = None
            self.refresh()
            return
        message = (
            gettext("Restore the previous CPU governors for this computer?")
            if restore
            else gettext(
                "Set CPU governors to performance for this computer?\n\n"
                "This affects all applications and can increase power use, heat, "
                "and fan noise. The change remains until restored, changed by "
                "another system service, or reset at reboot."
            )
        )
        answer = QMessageBox.question(
            QParent(self),
            gettext("CPU Performance"),
            message
            + "\n\n"
            + gettext("Your system may ask for administrator approval."),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        if not restore and self.previous is None:
            self.previous = current
        self.restoring = restore
        self.timed_out = False
        self.commands = commands
        self.busy = True
        for button in (
            self.performance_button,
            self.restore_button,
            self.refresh_button,
        ):
            button.disable()
        self.run_next()

    def run_next(self):
        if not self.commands:
            self.complete()
            return
        command = self.commands.pop(0)
        self.status_label.set_text(
            gettext("Waiting for administrator approval...")
        )
        self.timeout.start(120000)
        self.process.start(command[0], command[1:])
        self.process.closeWriteChannel()

    def on_process_finished(self, exit_code, exit_status):
        if not self.busy:
            return
        self.timeout.stop()
        if self.timed_out:
            self.complete(
                gettext(
                    "Administrator approval timed out. Check the current governor and restore previous settings if needed."
                )
            )
        elif exit_code != 0 or exit_status != QProcess.NormalExit:
            detail = (
                bytes(self.process.readAllStandardError())
                .decode("UTF-8", errors="replace")
                .strip()
            )
            message = gettext(
                "CPU governor change was cancelled or failed. Check the current governor; previous settings are still available to restore."
            )
            self.complete(
                message + ("\n\n" + detail[-2000:] if detail else "")
            )
        else:
            self.run_next()

    def on_process_error(self, error):
        if self.busy:
            self.timeout.stop()
            self.complete(
                gettext("Unable to run the CPU governor utility.")
                + "\n\n"
                + self.process.errorString()
            )

    def on_timeout(self):
        if self.busy:
            self.timed_out = True
            self.process.kill()

    def complete(self, error=None):
        self.timeout.stop()
        self.commands = []
        try:
            current = read_policies()
            if error is None:
                remaining = governor_commands(
                    current, self.previous if self.restoring else None
                )
                if remaining:
                    error = gettext(
                        "The requested governors were not applied, or another system service changed them. Check the current governor."
                    )
                elif self.restoring:
                    self.previous = None
        except (OSError, ValueError) as failure:
            error = error or str(failure)
        self.busy = False
        self.refresh()
        if error:
            fsui.show_error(error, gettext("CPU Performance"), parent=self)
