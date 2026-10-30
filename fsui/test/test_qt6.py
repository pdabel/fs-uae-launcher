import os
import unittest
from unittest.mock import Mock, call, patch

import fsui
from fsui.qt import QDialog, QFontMetrics, QImage, QPainter, QTimer
from fsui.qt.DrawingContext import DrawingContext
from fsui.qt.qt import configure_qt_environment
from .WidgetTestCase import WidgetTestCase


# What a lobby answers POST /game with, for tests that mock LobbyClient.
CREATED = {
    "id": "4d5211d9-2761-454c-b5aa-993264745dc4",
    "password": "8kmzbsfq",
    "players": 2,
    "port": "25101",
    "addresses": ["host.example"],
    "host_token": "host-token",
    "slot": 0,
    "player_token": "player-token",
}


class TestQtEnvironment(unittest.TestCase):
    def test_gnome_defaults_to_generic_theme(self):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}, clear=True):
            with patch("sys.platform", "linux"):
                configure_qt_environment()
                self.assertEqual(os.environ["QT_QPA_PLATFORMTHEME"], "generic")
                self.assertEqual(os.environ["QT_API"], "pyside6")

    def test_explicit_theme_is_preserved(self):
        environment = {
            "XDG_CURRENT_DESKTOP": "GNOME",
            "QT_QPA_PLATFORMTHEME": "qt6ct",
        }
        with patch.dict(os.environ, environment, clear=True):
            with patch("sys.platform", "linux"):
                configure_qt_environment()
                self.assertEqual(os.environ["QT_QPA_PLATFORMTHEME"], "qt6ct")

    def test_other_desktops_are_unchanged(self):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "KDE"}, clear=True):
            with patch("sys.platform", "linux"):
                configure_qt_environment()
                self.assertNotIn("QT_QPA_PLATFORMTHEME", os.environ)

    def test_other_platforms_are_unchanged(self):
        for platform in ("win32", "darwin"):
            with self.subTest(platform=platform):
                with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "GNOME"}, clear=True):
                    with patch("sys.platform", platform):
                        configure_qt_environment()
                        self.assertNotIn("QT_QPA_PLATFORMTHEME", os.environ)


class TestQt6(WidgetTestCase):
    def test_cpu_performance_confirmation_and_restore(self):
        from fsui.qt import QMessageBox
        from launcher.cpu_performance import CpuPolicy
        from launcher.settings.cpu_performance_group import CPUPerformanceGroup

        original = (CpuPolicy("policy0", "powersave", ("powersave", "performance"), (0, 1)),)
        performance = (CpuPolicy("policy0", "performance", ("powersave", "performance"), (0, 1)),)
        self.setup_dialog()
        with patch("launcher.settings.cpu_performance_group.read_policies", return_value=original) as read, \
                patch("launcher.settings.cpu_performance_group.QProcess") as process_class, \
                patch("launcher.cpu_performance.shutil.which", side_effect=lambda name: "/usr/bin/" + name):
            group = CPUPerformanceGroup(self.dialog)
            self.assertTrue(group.performance_button.is_enabled())
            self.assertFalse(group.restore_button.is_enabled())
            with patch("fsui.qt.QMessageBox.question", return_value=QMessageBox.No):
                group.performance_button.widget().click()
            process_class.return_value.start.assert_not_called()
            self.assertIsNone(group.previous)
            with patch("fsui.qt.QMessageBox.question", return_value=QMessageBox.Yes):
                group.performance_button.widget().click()
            process_class.return_value.start.assert_called_once_with(
                "/usr/bin/pkexec", ["--disable-internal-agent", "/usr/bin/cpupower", "--cpu", "0,1", "frequency-set", "--governor", "performance"]
            )
            self.assertTrue(group.busy)
            self.assertFalse(group.restore_button.is_enabled())
            read.return_value = performance
            group.on_process_finished(0, process_class.NormalExit)
            self.assertFalse(group.busy)
            self.assertTrue(group.restore_button.is_enabled())
            self.assertFalse(group.performance_button.is_enabled())
            self.assertEqual(group.previous, original)
            with patch("fsui.qt.QMessageBox.question", return_value=QMessageBox.Yes):
                group.restore_button.widget().click()
            self.assertEqual(process_class.return_value.start.call_args.args[1][-1], "powersave")
            read.return_value = original
            group.on_process_finished(0, process_class.NormalExit)
            self.assertIsNone(group.previous)
            self.assertTrue(group.performance_button.is_enabled())
        self.run_dialog()

    def test_cpu_performance_denial_retains_restore_snapshot(self):
        from fsui.qt import QMessageBox
        from launcher.cpu_performance import CpuPolicy
        from launcher.settings.cpu_performance_group import CPUPerformanceGroup

        original = (CpuPolicy("policy0", "powersave", ("powersave", "performance"), (0,)),)
        self.setup_dialog()
        with patch("launcher.settings.cpu_performance_group.read_policies", return_value=original), \
                patch("launcher.settings.cpu_performance_group.QProcess") as process_class, \
                patch("launcher.cpu_performance.shutil.which", side_effect=lambda name: "/usr/bin/" + name), \
                patch("fsui.show_error") as error:
            process_class.return_value.readAllStandardError.return_value = b"Not authorized"
            group = CPUPerformanceGroup(self.dialog)
            with patch("fsui.qt.QMessageBox.question", return_value=QMessageBox.Yes):
                group.performance_button.widget().click()
            group.on_process_finished(126, process_class.NormalExit)
            error.assert_called_once()
            self.assertFalse(group.busy)
            self.assertEqual(group.previous, original)
            self.assertTrue(group.restore_button.is_enabled())
        self.run_dialog()

    def test_cpu_performance_reports_missing_tools_and_cpu_controls(self):
        from launcher.cpu_performance import CpuPolicy
        from launcher.settings.cpu_performance_group import CPUPerformanceGroup

        original = (CpuPolicy("policy0", "powersave", ("powersave", "performance"), (0,)),)
        self.setup_dialog()
        with patch("launcher.settings.cpu_performance_group.read_policies", return_value=original) as read, \
                patch("launcher.settings.cpu_performance_group.QProcess") as process_class, \
                patch("launcher.cpu_performance.shutil.which", return_value=None):
            group = CPUPerformanceGroup(self.dialog)
            self.assertFalse(group.performance_button.is_enabled())
            self.assertIn("powersave", group.status_label._widget.text())
            self.assertIn("cpupower", group.status_label._widget.text())
            read.return_value = ()
            group.refresh()
            self.assertIn("unavailable", group.status_label._widget.text())
            process_class.return_value.start.assert_not_called()
        self.run_dialog()

    def test_cpu_performance_verifies_results_and_handles_timeout(self):
        from fsui.qt import QMessageBox
        from launcher.cpu_performance import CpuPolicy
        from launcher.settings.cpu_performance_group import CPUPerformanceGroup

        original = (CpuPolicy("policy0", "powersave", ("powersave", "performance"), (0,)),)
        self.setup_dialog()
        with patch("launcher.settings.cpu_performance_group.read_policies", return_value=original), \
                patch("launcher.settings.cpu_performance_group.QProcess") as process_class, \
                patch("launcher.cpu_performance.shutil.which", side_effect=lambda name: "/usr/bin/" + name), \
                patch("fsui.qt.QMessageBox.question", return_value=QMessageBox.Yes), \
                patch("fsui.show_error") as error:
            group = CPUPerformanceGroup(self.dialog)
            group.performance_button.widget().click()
            group.on_process_finished(0, process_class.NormalExit)
            self.assertIn("not applied", error.call_args.args[0])
            self.assertEqual(group.previous, original)
            error.reset_mock()
            group.performance_button.widget().click()
            group.on_timeout()
            process_class.return_value.kill.assert_called_once()
            group.on_process_finished(9, process_class.CrashExit)
            self.assertIn("timed out", error.call_args.args[0])
            self.assertFalse(group.busy)
            self.assertEqual(group.previous, original)
        self.run_dialog()

    def test_cleared_list_selection(self):
        class Items(fsui.VerticalItemView):
            def get_item_count(self):
                return 2

            def get_item_text(self, index):
                return ("First", "Second")[index]

        self.setup_dialog()
        list_view = fsui.ListView(self.dialog)
        list_view.set_items(["First", "Second"])
        item_view = Items(self.dialog)
        for view in (list_view, item_view):
            selected = []
            view.item_selected.connect(selected.append)
            view.set_index(0)
            self.assertTrue(selected)
            self.assertTrue(all(value == 0 for value in selected))
            selected.clear()
            view.set_index(None)
            self.assertTrue(selected)
            self.assertTrue(all(value is None for value in selected))
        self.run_dialog()

    def test_modern_dark_palette(self):
        from fsui.qt import QPalette
        from fsui.qt.modern_theme import apply_modern_theme

        palette = self.application.palette()
        stylesheet = self.application.styleSheet()
        font = self.application.font()
        try:
            apply_modern_theme(self.application)
            self.assertEqual(
                self.application.palette().color(QPalette.Window).name(),
                "#171923",
            )
            self.assertGreater(
                self.application.palette().color(QPalette.Text).lightness(),
                self.application.palette().color(QPalette.Base).lightness(),
            )
        finally:
            self.application.setPalette(palette)
            self.application.setStyleSheet(stylesheet)
            self.application.setFont(font)

    def test_status_text_uses_live_window_text_palette(self):
        from fsui.qt import QColor, QPalette
        from launcher.ui.statusbar.StatusElement import StatusElement
        from launcher.ui.statusbar.WarningsElement import WarningsElement

        class WarningStatusElement(StatusElement):
            paint_element = WarningsElement.paint_element

        self.setup_dialog()
        parent = fsui.Panel(self.dialog)
        status = StatusElement(parent)
        status.text = "Active status"
        warning = WarningStatusElement(parent)
        warning.coordinates = []
        warning.warnings = [(0, "Warning message", "")]
        icon = QImage(16, 16, QImage.Format_ARGB32)
        icon.fill(QColor("#ff8800"))
        warning.icons = [fsui.Image(object=icon)]
        image = QImage(320, 40, QImage.Format_ARGB32)
        image.fill(QColor("#171923"))
        painter = QPainter(image)
        try:
            context = DrawingContext(painter)
            with patch("launcher.ui.statusbar.StatusBar.StatusBar.draw_element_background"):
                for element in (status, warning):
                    for color in ("#edf0f7", "#123456"):
                        with self.subTest(element=type(element).__name__, color=color):
                            palette = element.widget().palette()
                            palette.setColor(QPalette.WindowText, QColor(color))
                            element.widget().setPalette(palette)
                            with patch.object(element, "create_dc", return_value=context):
                                with patch.object(context, "draw_text", wraps=context.draw_text) as draw_text:
                                    element.on_paint()
                                    draw_text.assert_called_once()
                            self.assertEqual(context.get_text_color(), QColor(color))
                status.active = False
                with patch.object(status, "create_dc", return_value=context):
                    status.on_paint()
                self.assertEqual(context.get_text_color(), QColor("#808080"))
        finally:
            painter.end()
        self.run_dialog()

    def test_theme_backgrounds_inherit_palette_across_platforms(self):
        from launcher.ui.skin import Skin

        for variant in ("modern", "plain", "windows311", "workbench"):
            for windows, macosx in ((True, False), (False, True), (False, False)):
                with self.subTest(variant=variant, windows=windows, macosx=macosx):
                    with patch.object(fsui, "theme_variant", variant):
                        with patch("fsbc.system.windows", windows), patch("fsbc.system.macosx", macosx):
                            with patch("launcher.ui.skin.LauncherSettings.get", return_value=""):
                                self.assertIsNone(Skin._get_background_color.__wrapped__(Skin))
                            with patch("launcher.ui.skin.LauncherSettings.get", return_value="#314159"):
                                self.assertEqual(
                                    Skin._get_background_color.__wrapped__(Skin).name(), "#314159"
                                )

    def test_modern_control_assets_and_interaction(self):
        from pathlib import Path
        from fsui.qt import QCheckBox, QComboBox, QIcon, QSpinBox
        from fsui.qt import modern_theme

        for name in ("check", "chevron-up", "chevron-down", "retro-chevron"):
            icon = QIcon(str(Path(modern_theme.__file__).parent / "res" / (name + ".svg")))
            self.assertFalse(icon.pixmap(16, 16).isNull())
        checkbox = QCheckBox("Default")
        checkbox.click()
        self.assertTrue(checkbox.isChecked())
        checkbox.setEnabled(False)
        checkbox.click()
        self.assertTrue(checkbox.isChecked())
        choice = QComboBox()
        choice.addItems(["Default", "On", "Off"])
        choice.setCurrentIndex(2)
        self.assertEqual(choice.currentText(), "Off")
        spinbox = QSpinBox()
        spinbox.setRange(0, 500)
        spinbox.setValue(200)
        spinbox.stepUp()
        self.assertEqual(spinbox.value(), 201)
        for control in (checkbox, choice, spinbox):
            control.deleteLater()

    def test_navigation_icon_variants(self):
        from fsui.qt import QIcon, QSize
        from launcher.ui.navigation_icons import navigation_icon

        images = {}
        for variant in ("modern", "plain", "windows311", "workbench"):
            with self.subTest(variant=variant), patch.object(fsui, "theme_variant", variant):
                icon = navigation_icon("fa5s.save")
                self.assertFalse(icon.isNull())
                for extent in (20, 24, 48):
                    for mode in (QIcon.Normal, QIcon.Selected, QIcon.Disabled):
                        image = icon.pixmap(QSize(extent, extent), mode).toImage()
                        self.assertEqual(image.size(), QSize(extent, extent))
                        self.assertTrue(any(
                            image.pixelColor(horizontal, vertical).alpha() > 0
                            for horizontal in range(extent)
                            for vertical in range(extent)
                        ))
                images[variant] = icon.pixmap(48, 48).toImage()
        self.assertNotEqual(images["windows311"], images["workbench"])
        self.assertNotEqual(images["modern"], images["workbench"])

    def test_retro_theme_selection(self):
        from fsui.qt import QPalette
        from fsui.qt.qt import initialize_qt_style

        palette = self.application.palette()
        stylesheet = self.application.styleSheet()
        font = self.application.font()
        theme, theme_variant = fsui.theme, fsui.theme_variant
        try:
            for variant, background, highlight in (
                ("windows311", "#c0c0c0", "#000080"),
                ("workbench", "#0055aa", "#ff8800"),
            ):
                for command_line in (False, True):
                    with self.subTest(variant=variant, command_line=command_line):
                        arguments = ["fs-uae-launcher"]
                        if command_line:
                            arguments.append("--launcher-theme=fusion-" + variant)
                        with patch("fsui.qt.qt.Settings.instance") as settings:
                            settings.return_value.get.side_effect = lambda key: (
                                ("fusion-modern" if command_line else "fusion-" + variant)
                                if key == "launcher_theme" else ""
                            )
                            with patch("sys.argv", arguments):
                                initialize_qt_style(self.application)
                        self.assertEqual(fsui.theme_variant, variant)
                        self.assertEqual(
                            self.application.palette().color(QPalette.Window).name(), background
                        )
                        self.assertEqual(
                            self.application.palette().color(QPalette.Highlight).name(), highlight
                        )
                        self.assertNotIn("@", self.application.styleSheet())
        finally:
            self.application.setPalette(palette)
            self.application.setStyleSheet(stylesheet)
            self.application.setFont(font)
            fsui.theme, fsui.theme_variant = theme, theme_variant

    def test_fusion_and_removed_theme_migration(self):
        from fsui.qt import QPalette
        from fsui.qt.qt import initialize_qt_style

        palette = self.application.palette()
        stylesheet = self.application.styleSheet()
        font = self.application.font()
        theme, variant = fsui.theme, fsui.theme_variant
        try:
            for saved in (
                "fusion-plain", "standard", "native", "fusion", "fusion-adwaita",
                "fusion-dark", "fusion-windows10", "fws", "unknown-theme",
            ):
                for command_line in (False, True):
                    with self.subTest(saved=saved, command_line=command_line):
                        arguments = ["fs-uae-launcher"]
                        if command_line:
                            arguments.append("--launcher-theme=" + saved)
                        with patch("fsui.qt.qt.Settings.instance") as settings:
                            settings.return_value.get.side_effect = lambda key: (
                                ("fusion-modern" if command_line else saved)
                                if key == "launcher_theme" else ""
                            )
                            with patch("sys.argv", arguments):
                                initialize_qt_style(self.application)
                            if saved != "fusion-plain":
                                settings.return_value.set.assert_called_with("launcher_theme", "fusion-plain")
                        self.assertEqual(fsui.theme_variant, "plain")
                        self.assertEqual(self.application.styleSheet(), "")
                        self.assertGreater(self.application.palette().color(QPalette.Window).lightness(), 150)
                        self.assertLess(self.application.palette().color(QPalette.Text).lightness(), 100)
        finally:
            self.application.setPalette(palette)
            self.application.setStyleSheet(stylesheet)
            self.application.setFont(font)
            fsui.theme, fsui.theme_variant = theme, variant

    def test_modern_information_icons(self):
        import qtawesome as qta
        from launcher.ui.HelpButton import HelpButton
        from launcher.ui.IconButton import IconButton

        self.setup_dialog()
        with patch.object(fsui, "theme_variant", "modern"):
            with patch("qtawesome.icon", wraps=qta.icon) as icons:
                help_button = HelpButton(self.dialog, "https://fs-uae.net/options")
                info_button = IconButton(self.dialog, "info.png")
                self.assertEqual(icons.call_count, 2)
                icons.assert_called_with("fa5s.info-circle", color="#9bcce2")
                for button in (help_button, info_button):
                    self.assertFalse(button.widget().icon().isNull())
                    self.assertEqual(button.widget().iconSize().width(), 18)
                with patch("launcher.ui.HelpButton.open_url_in_browser") as open_url:
                    help_button.widget().click()
                    open_url.assert_called_once_with("https://fs-uae.net/options")
        with patch.object(fsui, "theme_variant", "windows311"):
            with patch("qtawesome.icon") as icons:
                IconButton(self.dialog, "info.png")
                icons.assert_not_called()
        self.run_dialog()

    def test_image_button(self):
        self.setup_dialog()
        image = QImage(16, 16, QImage.Format_ARGB32)
        image.fill(fsui.Color(255, 0, 0))
        button = fsui.ImageButton(self.dialog, fsui.Image(object=image))
        calls = []
        button.activated.connect(lambda: calls.append(True))
        self.assertFalse(button.widget().icon().isNull())
        self.assertEqual(button.widget().iconSize().width(), 16)
        self.assertEqual(button.widget().iconSize().height(), 16)
        button.widget().click()
        self.assertEqual(calls, [True])
        button.set_image(fsui.Image(object=image))
        self.assertFalse(button.widget().icon().isNull())
        self.run_dialog()

    def test_launcher_new_button(self):
        from launcher.ui.newbutton import NewButton

        self.setup_dialog()
        button = NewButton(self.dialog)
        self.assertFalse(button.widget().icon().isNull())
        self.run_dialog()

    def test_screen_enumeration(self):
        desktop = self.application.desktop()
        screens = self.application.screens()
        self.assertEqual(desktop.screenCount(), len(screens))
        for index, screen in enumerate(screens):
            self.assertEqual(desktop.screenGeometry(index), screen.geometry())
        geometry = self.application.primaryScreen().virtualGeometry()
        self.assertEqual(
            fsui.get_screen_size(), (geometry.width(), geometry.height())
        )

    def test_text_measurement(self):
        self.setup_dialog()
        button = fsui.Button(self.dialog, "Measure")
        field = fsui.TextField(self.dialog, "Measure")
        for control in (button, field):
            widget = getattr(control, "_widget", control)
            metrics = QFontMetrics(widget.font())
            self.assertEqual(
                control.measure_text("Measure"),
                (metrics.horizontalAdvance("Measure"), metrics.height()),
            )
        self.run_dialog()

    def test_menu_callback(self):
        menu = fsui.Menu()
        calls = []
        menu.add_item("Run & Check", lambda: calls.append(True))
        action = menu.qmenu.actions()[0]
        self.assertEqual(action.text(), "Run && Check")
        action.trigger()
        self.assertEqual(calls, [True])

    def test_modal_dialog(self):
        dialog = fsui.Dialog(title="Qt 6")
        dialog.center_on_screen()
        QTimer.singleShot(0, lambda: dialog.end_modal(QDialog.Accepted))
        self.assertEqual(dialog.show_modal(), QDialog.Accepted)

    def test_window_centering(self):
        window = fsui.Window(None, title="Qt 6")
        window.set_size((400, 300))
        window.center_on_screen()
        self.assertEqual(
            window.real_window().frameGeometry().center(),
            window.real_window().screen().availableGeometry().center(),
        )
        window.close()

    def test_painting(self):
        image = QImage(200, 100, QImage.Format_ARGB32)
        image.fill(fsui.Color(255, 255, 255))
        painter = QPainter(image)
        try:
            context = DrawingContext(painter)
            context.draw_text("Qt 6", 0, 0)
            width, height = context.measure_text("Qt 6")
            self.assertGreater(width, 0)
            self.assertGreater(height, 0)
            context.draw_rectangle(10, 30, 20, 20, fsui.Color(255, 0, 0))
        finally:
            painter.end()
        self.assertEqual(image.pixelColor(15, 35), fsui.Color(255, 0, 0))


class TestLaunchAndNetplay(WidgetTestCase):
    def test_restart_command_and_shutdown_order(self):
        from types import SimpleNamespace
        from launcher.launcherapp import LauncherApp

        for frozen in (False, True):
            with self.subTest(frozen=frozen):
                application = SimpleNamespace(
                    _restart_arguments=None, qapplication=Mock(), save_settings=Mock()
                )
                calls = []
                application.save_settings.side_effect = lambda: calls.append("save")
                application.qapplication.closeAllWindows.side_effect = lambda: calls.append("close")
                application.qapplication.quit.side_effect = lambda: calls.append("quit")
                with patch("sys.argv", ["fs-uae-launcher", "--launcher-theme=fusion-modern", "game.adf"]):
                    with patch("sys.executable", "/test/python"), patch("sys.frozen", frozen, create=True):
                        with patch("fsboot.base_dir", return_value="/test/Amiga Data"):
                            LauncherApp.request_restart(application)
                            LauncherApp.request_restart(application)
                self.assertEqual(calls, ["save", "close", "quit"])
                self.assertEqual(application._restart_arguments[0], "/test/python")
                self.assertEqual(application._restart_arguments[-1], "--base-dir=/test/Amiga Data")
                self.assertEqual(len(application._restart_arguments), 2 if frozen else 3)
                self.assertNotIn("game.adf", application._restart_arguments)
                self.assertNotIn("--launcher-theme=fusion-modern", application._restart_arguments)
                with patch("launcher.launcherapp.os.execv") as execute:
                    LauncherApp.restart_if_requested(application)
                    execute.assert_called_once_with(
                        application._restart_arguments[0], application._restart_arguments
                    )

    def test_restart_save_failure_keeps_windows_open(self):
        from types import SimpleNamespace
        from launcher.launcherapp import LauncherApp

        application = SimpleNamespace(
            _restart_arguments=None, qapplication=Mock(),
            save_settings=Mock(side_effect=OSError("Disk full")),
        )
        with self.assertRaises(OSError):
            LauncherApp.request_restart(application)
        self.assertIsNone(application._restart_arguments)
        application.qapplication.closeAllWindows.assert_not_called()
        application.qapplication.quit.assert_not_called()
        with patch("launcher.launcherapp.os.execv") as execute:
            LauncherApp.restart_if_requested(application)
            execute.assert_not_called()

    def test_restart_runs_after_shutdown_notification(self):
        from launcher.apps.fs_uae_launcher import app_main

        for restart_failure in (False, True):
            with self.subTest(restart_failure=restart_failure):
                events = []
                with patch("launcher.launcherapp.LauncherApp") as application_class:
                    application = application_class.return_value
                    application.run.side_effect = lambda: events.append("run")
                    application.save_settings.side_effect = lambda: events.append("save")

                    def restart():
                        events.append("restart")
                        if restart_failure:
                            raise OSError("Executable unavailable")

                    application.restart_if_requested.side_effect = restart
                    with patch("fsbc.signal.Signal") as signal, patch("sys.argv", ["fs-uae-launcher"]):
                        signal.return_value.notify.side_effect = lambda: events.append("notify")
                        with patch("fsui.show_error") as show_error:
                            app_main()
                            self.assertEqual(events, ["run", "save", "notify", "restart"])
                            self.assertEqual(show_error.call_count, int(restart_failure))

    def test_portable_restart_copies_final_saved_settings(self):
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from launcher.launcherapp import LauncherApp
        from launcher.portable import PortableModeChange

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "original"
            data = source / "Data"
            data.mkdir(parents=True)
            settings = data / "Settings.ini"
            change = PortableModeChange(
                source, root / "portable data", root / "Portable.ini",
                True, root / "preferences" / "base-dir",
            )
            application = SimpleNamespace(
                _restart_arguments=None, qapplication=Mock(),
                save_settings=Mock(side_effect=lambda: settings.write_text("[settings]\nstate = saved\n")),
            )
            with patch("sys.argv", ["fs-uae-launcher"]), \
                    patch("fsboot.base_dir", return_value=str(source)), \
                    patch("launcher.scanner.Scanner.running", False):
                LauncherApp.request_restart(application, portable_change=change)
            self.assertFalse(change.marker.exists())
            settings.write_text("[settings]\nstate = final shutdown save\n")
            with patch("launcher.launcherapp.os.execv") as execute:
                LauncherApp.restart_if_requested(application)
                execute.assert_called_once()
            self.assertIn("final shutdown save", (change.destination / "Data" / "Settings.ini").read_text())
            self.assertEqual(application._restart_arguments[-1], "--base-dir=" + str(change.destination))

    def test_portable_restart_failure_does_not_relaunch(self):
        from types import SimpleNamespace
        from launcher.launcherapp import LauncherApp

        change = Mock()
        change.apply.side_effect = OSError("Disk full")
        application = SimpleNamespace(
            _restart_arguments=["python", "--base-dir=/original"],
            _portable_change=change, qapplication=Mock(),
        )
        with patch("launcher.launcherapp.os.execv") as execute:
            with self.assertRaisesRegex(OSError, "original data"):
                LauncherApp.restart_if_requested(application)
            execute.assert_not_called()
        self.assertEqual(application._restart_arguments[-1], "--base-dir=/original")

    def test_embedded_host_server_lifecycle(self):
        from launcher.netplay.netplay import Netplay
        from launcher.netplay.server_details import ServerDetails

        for action in ("stop", "reset", "disconnect"):
            with self.subTest(action=action):
                view = ServerDetails()
                parent = Mock(create_server_view=view.present)
                netplay = Netplay(parent=parent)
                netplay.irc.active_channel_name = "#embedded-game"
                channel = Mock()
                channel.is_op.return_value = True
                netplay.irc.active_channel = Mock(return_value=channel)
                try:
                    with patch.object(netplay, "require_game_channel", return_value=True), \
                            patch("launcher.netplay.netplay.LobbyClient") as client_class, \
                            patch("launcher.netplay.netplay.NetplaySession") as session_class:
                        client_class.return_value.create_game.return_value = CREATED
                        session_class.return_value.game_id = CREATED["id"]
                        with patch("launcher.netplay.netplay.Server") as server_class:
                            with patch("launcher.netplay.netplay.LauncherConfig.set_multiple"):
                                with patch.object(view, "show", wraps=view.show) as show_view:
                                    server = server_class.return_value
                                    server.players = 2
                                    server.port = 25101
                                    server.process = None
                                    netplay.command_hostgame(["127.0.0.1:25101", "2"])
                                    server.start.assert_called_once_with()
                                    show_view.assert_called_once_with()
                                    self.assertIs(netplay.game_window, view)
                                    self.assertEqual(view.fields["port"].text(), "25101")
                                    self.assertEqual(view.fields["players"].text(), "2")
                                    self.assertEqual(view.fields["channel"].text(), "#embedded-game")
                                    self.assertEqual(view.fields["game_id"].text(), CREATED["id"])
                                    self.assertTrue(view.stop_button.isEnabled())
                                    if action == "stop":
                                        view.stop_button.click()
                                    elif action == "reset":
                                        netplay.command_reset([])
                                    else:
                                        netplay.disconnect()
                                    server.stop.assert_called_once_with()
                                    self.assertFalse(view.stop_button.isEnabled())
                                    self.assertIsNone(view.server)
                finally:
                    if Netplay.current() is netplay:
                        netplay.disconnect()
                    view.deleteLater()

    def test_hosted_lobby_outlives_a_running_game_left_in_it(self):
        from launcher.netplay.netplay import Netplay
        from launcher.netplay.server_details import ServerDetails

        for started in (True, False):
            with self.subTest(started=started):
                view = ServerDetails()
                netplay = Netplay(parent=Mock(create_server_view=view.present))
                netplay.irc.active_channel_name = "#first-game"
                channel = Mock()
                channel.is_op.return_value = True
                netplay.irc.active_channel = Mock(return_value=channel)
                try:
                    with patch.object(netplay, "require_game_channel", return_value=True), \
                            patch("launcher.netplay.netplay.LobbyClient") as client_class, \
                            patch("launcher.netplay.netplay.NetplaySession") as session_class, \
                            patch("launcher.netplay.netplay.Server") as server_class, \
                            patch("launcher.netplay.netplay.LauncherConfig.set_multiple"):
                        client = client_class.return_value
                        client.create_game.return_value = CREATED
                        session_class.return_value.game_id = CREATED["id"]
                        session_class.return_value.started = started
                        server = server_class.return_value
                        server.players = 2
                        server.port = 25101
                        server.public_addresses = "127.0.0.1"
                        server.process.poll.return_value = None

                        netplay.command_hostgame(["127.0.0.1:25101", "2"])
                        # What joining another game channel does.
                        netplay.end_session()
                        if not started:
                            # Its game never ran: the lobby goes with it.
                            server.stop.assert_called_once_with()
                            self.assertIsNone(view.server)
                            continue
                        server.stop.assert_not_called()
                        self.assertIs(view.server, server)

                        # Another port or address would need a new lobby,
                        # which would end the game still in this one.
                        netplay.command_hostgame(["127.0.0.1:25200", "2"])
                        self.assertIn("still running", channel.warning.call_args.args[0])
                        self.assertEqual(client.create_game.call_count, 1)

                        netplay.irc.active_channel_name = "#second-game"
                        netplay.command_hostgame(["127.0.0.1:25101", "3"])
                        server_class.assert_called_once()
                        server.start.assert_called_once_with()
                        self.assertEqual(client.create_game.call_count, 2)
                        server.stop.assert_not_called()
                        self.assertIs(view.server, server)
                        self.assertEqual(view.fields["players"].text(), "3")
                        self.assertEqual(view.fields["channel"].text(), "#second-game")

                        netplay.command_reset([])
                        server.stop.assert_called_once_with()
                finally:
                    if Netplay.current() is netplay:
                        netplay.disconnect()
                    view.deleteLater()

    def test_hostgame_runs_a_local_lobby_and_announces_the_game(self):
        from launcher.launcher_config import LauncherConfig
        from launcher.netplay.netplay import HOST_PORT, Netplay

        parent = Mock()
        netplay = Netplay(parent=parent)
        netplay.irc.my_nick = "HostNick"
        netplay.game_channel = "#shared-game"
        channel = Mock()
        channel.is_op.return_value = True
        netplay.irc.active_channel = Mock(return_value=channel)
        netplay.irc.channel = Mock(return_value=channel)
        netplay.irc.active_channel_name = "#shared-game"
        try:
            with patch.object(netplay, "require_game_channel", return_value=True), \
                    patch("launcher.netplay.netplay.LobbyClient") as client_class, \
                    patch("launcher.netplay.netplay.NetplaySession") as session_class:
                client = client_class.return_value
                client.create_game.return_value = dict(CREATED, password="secret")
                session_class.return_value.game_id = CREATED["id"]
                session_class.return_value.is_host = True
                with patch("launcher.netplay.netplay.Server") as server_class:
                    server_class.return_value.port = HOST_PORT
                    with patch("launcher.netplay.netplay.LauncherConfig.set_multiple") as set_config:
                        netplay.command_hostgame(["host.example", "2", "secret"])
                        server_class.assert_called_once_with(
                            HOST_PORT, 2, "secret", lobby=True,
                            public_addresses="host.example",
                        )
                        server_class.return_value.start.assert_called_once_with()
                        # The launcher reaches its own lobby on loopback.
                        client_class.assert_called_once_with("127.0.0.1", HOST_PORT)
                        client.create_game.assert_called_once_with(
                            2, "secret", "HostNick",
                            LauncherConfig.sync_keys_list,
                            LauncherConfig.checksum_keys,
                        )
                        self.assertEqual(dict(set_config.call_args.args[0]), {
                            "__netplay_game": CREATED["id"],
                            "__netplay_password": "secret",
                            "__netplay_players": "2",
                            "__netplay_port": str(HOST_PORT),
                            "__netplay_host": "",
                            "__netplay_addresses": "host.example",
                        })
                        session_class.return_value.start.assert_called_once_with()
                        self.assertEqual(
                            session_class.call_args.kwargs["host_token"], "host-token"
                        )
                        # Players are pointed at the public address.
                        channel.privmsg.assert_called_once_with(
                            f"__session host.example:{HOST_PORT} {CREATED['id']}"
                        )
                        parent.create_server_view.assert_called_once()
                        netplay.game_window.show.assert_called_once_with()
        finally:
            netplay.disconnect()

    def test_hostgame_start_failure_does_not_publish_game(self):
        from launcher.netplay.netplay import Netplay
        from launcher.server.Server import PortInUseError, ServerError

        # A server error's details can be paths and build guidance, longer
        # than an IRC line: they stay local, and the channel gets a summary.
        for error, message, local_only in (
            (PortInUseError(25101, "Address in use"), "netplay lobby", None),
            (
                ServerError("Missing binary"),
                "could not start the netplay server",
                "Missing binary",
            ),
        ):
            with self.subTest(error=type(error).__name__):
                parent = Mock()
                netplay = Netplay(parent=parent)
                channel = Mock()
                channel.is_op.return_value = True
                netplay.irc.active_channel = Mock(return_value=channel)
                try:
                    with patch.object(netplay, "require_game_channel", return_value=True):
                        with patch("launcher.netplay.netplay.Server") as server_class:
                            with patch("launcher.netplay.netplay.LauncherConfig.set_multiple") as set_config:
                                server_class.return_value.start.side_effect = error
                                netplay.command_hostgame(["127.0.0.1", "2"])
                                parent.create_server_view.assert_not_called()
                                set_config.assert_not_called()
                                channel.info.assert_not_called()
                                channel.privmsg.assert_called_once()
                                self.assertIn(message, channel.privmsg.call_args.args[0])
                                if local_only is not None:
                                    self.assertNotIn(local_only, channel.privmsg.call_args.args[0])
                                    self.assertIn(local_only, channel.warning.call_args.args[0])
                                self.assertIsNone(netplay.game_window)
                finally:
                    netplay.disconnect()

    def test_startgame_creates_a_lobby_game(self):
        from launcher.netplay.netplay import Netplay

        netplay = Netplay()
        netplay.irc.my_nick = "HostNick"
        netplay.game_channel = "#test-game"
        channel = Mock()
        channel.is_op.return_value = True
        netplay.irc.active_channel = Mock(return_value=channel)
        netplay.irc.channel = Mock(return_value=channel)
        try:
            with patch.object(netplay, "require_game_channel", return_value=True), \
                    patch("launcher.netplay.netplay.LobbyClient") as client_class, \
                    patch("launcher.netplay.netplay.NetplaySession") as session_class:
                client_class.return_value.create_game.return_value = CREATED
                session_class.return_value.game_id = CREATED["id"]
                session_class.return_value.is_host = True
                with patch("launcher.netplay.netplay.LauncherConfig.set_multiple") as set_config:
                    netplay.command_startgame(["lobby.example:25101", "2"])
                    client_class.assert_called_once_with("lobby.example", 25101)
                    # No password given: the lobby generates one, which is
                    # what the host and every player use.
                    self.assertEqual(
                        client_class.return_value.create_game.call_args.args[1], ""
                    )
                    self.assertEqual(
                        dict(set_config.call_args.args[0])["__netplay_password"],
                        CREATED["password"],
                    )
                    channel.info.assert_called_once()
                    channel.privmsg.assert_called_once_with(
                        f"__session lobby.example:25101 {CREATED['id']}"
                    )
        finally:
            netplay.disconnect()

    def test_server_details_detects_process_exit(self):
        from launcher.netplay.server_details import ServerDetails

        view = ServerDetails()
        server = Mock(players=2)
        server.process.poll.return_value = 1
        view.present(None, server, "test-game-id", 25101, "#test-game")
        view._check_server()
        server.stop.assert_called_once_with()
        self.assertFalse(view.stop_button.isEnabled())
        self.assertIsNone(view.server)
        view.deleteLater()

    def test_netplay_column_sizes_and_persistence(self):
        import json
        from fsui.qt import QEvent
        from launcher.netplay.netplay import Netplay
        from launcher.netplay.netplay_page import NetplayPage

        with patch.object(Netplay, "_current", None), patch.object(Netplay, "connect"):
            with patch("launcher.netplay.netplay_page.LauncherSettings.get", return_value=""), patch("launcher.netplay.netplay_page.LauncherSettings.set") as save:
                window = fsui.Window(None, title="Netplay columns")
                window.layout = fsui.VerticalLayout()
                page = NetplayPage(window)
                window.layout.add(page, fill=True, expand=True)
                window.set_size((1500, 850))
                window.show()
                self.application.processEvents()
                try:
                    self.assertEqual(page.splitter.count(), 3)
                    sizes = page.splitter.sizes()
                    for actual, expected in zip(sizes, (0.25, 0.4, 0.35)):
                        self.assertAlmostEqual(actual / sum(sizes), expected, delta=0.02)
                    self.assertIs(page.channel_area.widget(), page.panel.channel_panel.widget())
                    self.assertIs(page.chat_area.widget(), page.panel.widget())
                    self.assertIs(page.details_area.widget(), page.server_details)
                    page.splitter.moveSplitter(450, 1)
                    self.application.processEvents()
                    save.assert_called()
                    self.assertEqual(save.call_args.args[0], "netplay_column_sizes")
                    saved = json.loads(save.call_args.args[1])
                    self.assertEqual(saved, page.splitter.sizes())
                    page._column_sizes = saved
                    window.set_size((1200, 800))
                    self.application.processEvents()
                    page._restore_column_sizes()
                    sizes = page.splitter.sizes()
                    for actual, expected in zip(sizes, saved):
                        self.assertAlmostEqual(actual / sum(sizes), expected / sum(saved), delta=0.03)
                finally:
                    page.shutdown()
                    window.close()
                    self.application.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_netplay_saved_column_sizes(self):
        from fsui.qt import QEvent
        from launcher.netplay.netplay import Netplay
        from launcher.netplay.netplay_page import NetplayPage

        cases = (
            ("[300, 500, 400]", [300, 500, 400]),
            ("", [25, 40, 35]),
            ("invalid", [25, 40, 35]),
            ("[0, 40, 35]", [25, 40, 35]),
            ("[true, 40, 35]", [25, 40, 35]),
            ("[25, 40]", [25, 40, 35]),
            ("[25, 40, 1000001]", [25, 40, 35]),
        )
        for stored, expected in cases:
            with self.subTest(stored=stored), patch.object(Netplay, "_current", None), patch.object(Netplay, "connect"):
                with patch("launcher.netplay.netplay_page.LauncherSettings.get", return_value=stored), patch("launcher.netplay.netplay_page.LauncherSettings.set") as save:
                    window = fsui.Window(None, title="Saved netplay columns")
                    window.layout = fsui.VerticalLayout()
                    page = NetplayPage(window)
                    window.layout.add(page, fill=True, expand=True)
                    window.set_size((1500, 850))
                    window.show()
                    self.application.processEvents()
                    try:
                        self.assertEqual(page._column_sizes, expected)
                        sizes = page.splitter.sizes()
                        for actual, weight in zip(sizes, expected):
                            self.assertAlmostEqual(actual / sum(sizes), weight / sum(expected), delta=0.02)
                        save.assert_not_called()
                    finally:
                        page.shutdown()
                        window.close()
                        self.application.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_netplay_columns_role_geometry(self):
        from fsui.qt import QEvent
        from fsui.qt.modern_theme import apply_modern_theme
        from fsui.qt.retro_theme import apply_retro_theme
        from launcher.netplay.irc import LOBBY_CHANNEL
        from launcher.netplay.netplay import Netplay
        from launcher.netplay.netplay_page import NetplayPage

        palette = self.application.palette()
        stylesheet = self.application.styleSheet()
        font = self.application.font()
        try:
            for variant in ("modern", "plain", "windows311", "workbench"):
                self.application.setStyleSheet("")
                self.application.setPalette(self.application.style().standardPalette())
                self.application.setFont(font)
                if variant == "modern":
                    apply_modern_theme(self.application)
                elif variant != "plain":
                    apply_retro_theme(self.application, variant)
                with self.subTest(theme=variant), patch.object(fsui, "theme_variant", variant), patch.object(Netplay, "_current", None), patch.object(Netplay, "connect"):
                    with patch("launcher.netplay.netplay_page.LauncherSettings.get", return_value=""):
                        window = fsui.Window(None, title="Netplay role layout")
                        window.layout = fsui.VerticalLayout()
                        page = NetplayPage(window)
                        window.layout.add(page, fill=True, expand=True)
                        window.show()
                        try:
                            for width in (800, 1000, 1500):
                                window.set_size((width, 850))
                                for channel, operator in ((LOBBY_CHANNEL, False), ("#layout-game", False), ("#layout-game", True), ("#layout-daf", False), ("#layout-daf", True)):
                                    with self.subTest(width=width, channel=channel, operator=operator), patch.object(page.panel.netplay, "is_op", return_value=operator):
                                        page.panel.active_channel = channel
                                        page.panel.update_action_buttons_visibility()
                                        self.application.processEvents()
                                        self.assertEqual(page.channel_area.horizontalScrollBar().maximum(), 0)
                                        self.assertTrue(page.channel_area.widget().isAncestorOf(page.panel.join_channel_button.widget()))
                                        self.assertTrue(page.details_area.widget().isAncestorOf(page.panel.host_game_button.widget()))
                                        self.assertTrue(page.chat_area.widget().isAncestorOf(page.panel.input_field))
                                        self.assertFalse(hasattr(page.panel, "reset_button"))
                                        controls_geometry = page.panel.game_panel.widget().geometry()
                                        stop_geometry = page.server_details.stop_button.geometry()
                                        self.assertGreaterEqual(stop_geometry.top() - controls_geometry.bottom() - 1, 10)
                                        self.assertLessEqual(stop_geometry.top() - controls_geometry.bottom() - 1, 12)
                                        if operator:
                                            self.assertEqual(page.panel.port_field.x(), page.panel.player_count_field.x())
                                            self.assertEqual(page.panel.port_field.width(), page.panel.player_count_field.width())
                                            self.assertGreaterEqual(page.panel.port_field.x() - page.panel.port_label.geometry().right() - 1, 20)
                                        previous = None
                                        for control in (page.panel.host_game_button, page.panel.start_button, page.panel.recheck_button):
                                            if control.visible():
                                                geometry = control.widget().geometry()
                                                self.assertGreater(geometry.width(), 0)
                                                self.assertLessEqual(geometry.right(), page.panel.game_panel.widget().width())
                                                if previous is not None:
                                                    self.assertFalse(previous.intersects(geometry))
                                                    self.assertGreaterEqual(geometry.top() - previous.bottom() - 1, 10)
                                                previous = geometry
                        finally:
                            page.shutdown()
                            window.close()
                            self.application.sendPostedEvents(None, QEvent.DeferredDelete)
        finally:
            self.application.setPalette(palette)
            self.application.setStyleSheet(stylesheet)
            self.application.setFont(font)

    def test_irc_names_reply_updates_operator_controls(self):
        from launcher.netplay.irc import LOBBY_CHANNEL
        from launcher.netplay.irc_broadcaster import IRCBroadcaster
        from launcher.netplay.netplay import Netplay
        from launcher.netplay.netplay_panel import NetplayPanel
        from fsui.qt import QCoreApplication, QEvent

        with patch.object(IRCBroadcaster, "irc_listeners", []):
            with patch.object(Netplay, "_current", None):
                window = fsui.Window(None, title="IRC operator test")
                window.layout = fsui.VerticalLayout()
                panel = NetplayPanel(window, header=False)
                window.layout.add(panel, fill=True, expand=True)
                window.set_size((1100, 800))
                window.show()
                self.application.processEvents()
                irc = panel.netplay.irc
                irc.my_nick = "ReplayUser"
                irc.client = Mock()
                try:
                    irc.irc_join("ReplayUser!user@localhost", LOBBY_CHANNEL)
                    irc.irc_namreply(
                        "server", "ReplayUser", "=", LOBBY_CHANNEL,
                        "@ReplayUser",
                    )
                    self.assertEqual(panel.nick_list.get_item(0), "@ReplayUser")
                    irc.irc_join("ReplayUser!user@localhost", "#replay-hst")
                    self.assertFalse(panel.netplay.is_op())
                    irc.irc_namreply(
                        "server", "ReplayUser", "=", "#replay-hst",
                        "@ReplayUser",
                    )
                    self.application.processEvents()
                    self.assertTrue(panel.netplay.is_op())
                    self.assertEqual(panel.nick_list.get_item(0), "@ReplayUser")
                    self.assertIn("You are the Operator", panel.text_area.get_text())
                    for control in (
                        panel.host_game_button,
                        panel.start_button, panel.recheck_button,
                    ):
                        self.assertTrue(control.visible())
                        self.assertGreater(control.widget().geometry().y(), 0)
                    irc.irc_mode("server", "#replay-hst", "-o", "ReplayUser")
                    self.assertFalse(panel.netplay.is_op())
                    self.assertFalse(panel.host_game_button.visible())
                    self.assertFalse(panel.start_button.visible())
                    self.assertTrue(panel.recheck_button.visible())
                    irc.irc_mode("server", "#replay-hst", "+o", "ReplayUser")
                    self.assertTrue(panel.netplay.is_op())
                    self.assertTrue(panel.host_game_button.visible())
                finally:
                    window.close()
                    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_default_chat_color_uses_current_palette(self):
        from fsui.qt import QColor, QPalette
        from launcher.netplay.irc_color import IRCColor

        self.setup_dialog()
        text = fsui.TextArea(self.dialog)
        for color in ("#edf0f7", "#121212"):
            palette = text.palette()
            palette.setColor(QPalette.Text, QColor(color))
            text.setPalette(palette)
            text.append_text("Joined channel", color=(64, 164, 64))
            text.append_text("You are the Operator", color=IRCColor.MESSAGE)
            self.assertEqual(text.textColor(), QColor(color))
        self.run_dialog()

    def test_start_button_dispatch(self):
        from launcher.ui.launch import StartButton

        self.setup_dialog()
        button = StartButton(self.dialog, Mock())
        with patch("launcher.launcherapp.LauncherApp.start_game") as start:
            button.widget().click()
            start.assert_called_once_with()
        self.run_dialog()

    def test_launch_dialog_netplay_context(self):
        from launcher.ui.launch import LaunchDialog

        for channel in (None, "#test-game"):
            with self.subTest(channel=channel):
                netplay = Mock(game_channel=channel) if channel else None
                with patch("launcher.ui.launch.Netplay.current", return_value=netplay):
                    with patch("launcher.ui.launch.LauncherConfig"):
                        task = Mock()
                        dialog = LaunchDialog(None, "Launching test", task)
                        self.assertEqual(dialog.netplay_channel, channel)
                        task.progressed.connect.assert_called_once_with(dialog.on_progress)
                        task.finished.connect.assert_called_once_with(dialog.on_complete)
                        task.failed.connect.assert_called_once_with(dialog.on_error)
                        dialog.was_closed = True
                        dialog.close()

    def test_join_channel_uses_current_game_title(self):
        from launcher.netplay.netplay_panel import JoinChannelButton
        from launcher.option import Option

        self.setup_dialog()
        irc = Mock()
        button = JoinChannelButton(self.dialog, irc)
        cases = (
            ("Barbarian", "DAF", "#barbarian-daf", "#barbarian-daf", "/join #barbarian-daf"),
            ("  Shadow of the Beast  ", " PL2 ", "#my-game-pl2", "#shadow-of-the-beast-pl2", "/join #my-game-pl2"),
            ("Lotus Turbo Challenge", "", "#lotus-turbo-challenge-unk", "#lotus-turbo-challenge-unk", "/join #lotus-turbo-challenge-unk"),
            ("Barbarian", " # D_AF! ", "#barbarian-daf", "#barbarian-daf", "/join #barbarian-daf"),
            ("Barbarian", "ABCD", "#barbarian-abc", "#barbarian-abc", "/join #barbarian-abc"),
            ("Barbarian", "!!!", "#barbarian-unk", "#barbarian-unk", "/join #barbarian-unk"),
            ("", "DAF", None, "#new-daf", None),
            ("   ", "DAF", "", "#new-daf", None),
        )
        for title, tag, response, expected_default, expected_command in cases:
            settings = {Option.CONFIG_NAME: title, Option.NETPLAY_TAG: tag}
            with self.subTest(title=title, tag=tag), patch("launcher.netplay.netplay_panel.LauncherSettings.get", side_effect=settings.__getitem__) as get_setting:
                with patch("launcher.netplay.netplay_panel.SimpleTextInputDialog.get_text", return_value=response) as prompt:
                    irc.reset_mock()
                    button.widget().click()
                    self.assertEqual(get_setting.call_args_list[0].args, (Option.CONFIG_NAME,))
                    self.assertEqual(prompt.call_args.kwargs["default_text"], expected_default)
                    irc.handle_command.assert_not_called()
                    if expected_command is None:
                        irc.join.assert_not_called()
                        self.assertEqual(
                            get_setting.call_args_list,
                            [
                                call(Option.CONFIG_NAME),
                                call(Option.NETPLAY_TAG),
                            ],
                        )
                    else:
                        irc.join.assert_called_once_with(expected_command.removeprefix("/join "), private=False)
                        self.assertEqual(get_setting.call_args_list[1].args, (Option.NETPLAY_TAG,))
        self.run_dialog()

    def test_netplay_command_history_keys_and_clear(self):
        import tempfile
        from pathlib import Path
        from qtpy.QtTest import QTest
        from fsui.qt import QMessageBox, Qt
        from launcher.netplay.command_history import CommandHistory
        from launcher.netplay.netplay_panel import NetplayPanel

        self.setup_dialog()
        with tempfile.TemporaryDirectory() as temporary, \
                patch("launcher.netplay.netplay_panel.Netplay") as netplay_class, \
                patch("launcher.netplay.netplay_panel.CommandHistory", return_value=CommandHistory(Path(temporary) / "history.sqlite")):
            panel = NetplayPanel(self.dialog, header=False)
            netplay = netplay_class.return_value
            netplay.handle_command.return_value = True
            field = panel.input_field
            try:
                for command in ("/join #amiga", "/hostgame localhost:25101 2"):
                    field.set_text(command)
                    QTest.keyClick(field, Qt.Key_Return)
                self.assertEqual(netplay.handle_command.call_count, 2)
                self.assertEqual(field.get_text(), "")
                field.set_text("unfinished draft")
                QTest.keyClick(field, Qt.Key_Up)
                self.assertEqual(field.get_text(), "/hostgame localhost:25101 2")
                QTest.keyClick(field, Qt.Key_Up)
                self.assertEqual(field.get_text(), "/join #amiga")
                QTest.keyClick(field, Qt.Key_Down)
                QTest.keyClick(field, Qt.Key_Down)
                self.assertEqual(field.get_text(), "unfinished draft")
                self.assertEqual(netplay.handle_command.call_count, 2)
                QTest.keyClick(field, Qt.Key_Up)
                QTest.keyClicks(field, " edited")
                self.assertIsNone(panel.command_history.position)
                with patch("fsui.qt.QMessageBox.question", return_value=QMessageBox.No):
                    panel.clear_history_button.widget().click()
                self.assertEqual(panel.command_history.previous("draft"), "/hostgame localhost:25101 2")
                field.set_text("/hostgame localhost:25101 2")
                with patch("fsui.qt.QMessageBox.question", return_value=QMessageBox.Yes):
                    panel.clear_history_button.widget().click()
                self.assertEqual(field.get_text(), "draft")
                QTest.keyClick(field, Qt.Key_Up)
                self.assertEqual(field.get_text(), "draft")
                self.assertFalse(panel.clear_history_button.widget().icon().isNull())
            finally:
                panel.on_destroy()
        self.run_dialog()

    def test_netplay_history_button_shares_input_row(self):
        from launcher.netplay.netplay_panel import NetplayPanel

        self.setup_dialog()
        self.dialog.layout = fsui.VerticalLayout()
        with patch("launcher.netplay.netplay_panel.Netplay"):
            panel = NetplayPanel(self.dialog, header=False)
            self.dialog.layout.add(panel, fill=True, expand=True)
            self.dialog.show()
            for width in (540, 800, 1000):
                with self.subTest(width=width):
                    self.dialog.set_size((width, 600))
                    self.application.processEvents()
                    field = panel.input_field.geometry()
                    button = panel.clear_history_button.widget().geometry()
                    self.assertLessEqual(abs(field.center().y() - button.center().y()), 1)
                    self.assertEqual(button.left() - field.right() - 1, 10)
                    self.assertGreater(field.width(), 120)
                    self.assertLess(button.right(), panel.widget().width())
                    self.assertLess(button.bottom(), panel.widget().height())
                    self.assertFalse(field.intersects(button))
        self.run_dialog()

    def test_netplay_history_icon_is_centered(self):
        from fsui.qt.modern_theme import apply_modern_theme
        from launcher.netplay.netplay_panel import NetplayPanel

        palette = self.application.palette()
        stylesheet = self.application.styleSheet()
        font = self.application.font()
        self.setup_dialog()
        try:
            apply_modern_theme(self.application)
            with patch("launcher.netplay.netplay_panel.Netplay"):
                panel = NetplayPanel(self.dialog, header=False)
                button = panel.clear_history_button.widget()
                try:
                    image = button.grab().toImage()
                    pixels = [
                        (horizontal, vertical)
                        for horizontal in range(4, image.width() - 4)
                        for vertical in range(4, image.height() - 4)
                        if all(channel > 170 for channel in image.pixelColor(horizontal, vertical).getRgb()[:3])
                    ]
                    self.assertTrue(pixels)
                    for axis, size in ((0, image.width()), (1, image.height())):
                        center = (min(pixel[axis] for pixel in pixels) + max(pixel[axis] for pixel in pixels)) / 2
                        self.assertAlmostEqual(center, (size - 1) / 2, delta=1.5)
                finally:
                    panel.on_destroy()
        finally:
            self.application.setPalette(palette)
            self.application.setStyleSheet(stylesheet)
            self.application.setFont(font)
        self.run_dialog()

    def test_netplay_history_failure_does_not_block_commands(self):
        import sqlite3
        from qtpy.QtTest import QTest
        from fsui.qt import QMessageBox, Qt
        from launcher.netplay.netplay_panel import NetplayPanel

        self.setup_dialog()
        with patch("launcher.netplay.netplay_panel.Netplay") as netplay_class, \
                patch("launcher.netplay.netplay_panel.CommandHistory") as history_class:
            panel = NetplayPanel(self.dialog, header=False)
            netplay = netplay_class.return_value
            netplay.handle_command.return_value = False
            history = history_class.return_value
            history.add.side_effect = sqlite3.OperationalError("Database locked")
            history.previous.side_effect = sqlite3.OperationalError("Database locked")
            try:
                panel.input_field.set_text("/join #amiga")
                QTest.keyClick(panel.input_field, Qt.Key_Return)
                netplay.irc.handle_command.assert_called_once_with("/join #amiga")
                self.assertEqual(panel.input_field.get_text(), "")
                panel.input_field.set_text("keep this draft")
                QTest.keyClick(panel.input_field, Qt.Key_Up)
                self.assertEqual(panel.input_field.get_text(), "keep this draft")
                self.assertEqual(netplay.irc.warning.call_count, 2)
                history.clear.side_effect = sqlite3.OperationalError("Database locked")
                with patch("fsui.qt.QMessageBox.question", return_value=QMessageBox.Yes), \
                        patch("fsui.show_error") as error:
                    panel.clear_history_button.widget().click()
                    error.assert_called_once()
                self.assertEqual(panel.input_field.get_text(), "keep this draft")
            finally:
                panel.on_destroy()
        self.run_dialog()

    def test_join_channel_private_checkbox(self):
        from launcher.netplay.netplay_panel import NetplayPanel
        from launcher.option import Option

        self.setup_dialog()
        with patch("launcher.netplay.netplay_panel.Netplay") as netplay_class:
            panel = NetplayPanel(self.dialog, header=False, columns=True)
            irc = netplay_class.return_value.irc
            self.assertFalse(panel.private_game_checkbox.is_checked())
            values = {Option.CONFIG_NAME: "Barbarian", Option.NETPLAY_TAG: "DAF"}
            with patch("launcher.netplay.netplay_panel.LauncherSettings.get", side_effect=values.__getitem__):
                accept_default = lambda *args, default_text, **kwargs: default_text
                with patch("launcher.netplay.netplay_panel.SimpleTextInputDialog.get_text", side_effect=accept_default):
                    for private in (False, True):
                        with self.subTest(private=private):
                            irc.reset_mock()
                            panel.private_game_checkbox.check(private)
                            panel.join_channel_button.widget().click()
                            irc.join.assert_called_once_with("#barbarian-daf", private=private)
                            irc.handle_command.assert_not_called()
                with patch("launcher.netplay.netplay_panel.SimpleTextInputDialog.get_text", return_value=None):
                    irc.reset_mock()
                    panel.join_channel_button.widget().click()
                    irc.join.assert_not_called()
                    irc.handle_command.assert_not_called()
            panel.on_destroy()
        self.run_dialog()

    def test_join_channel_dialog_selects_default_title(self):
        from fsui.qt import QEvent
        from launcher.netplay.netplay_panel import SimpleTextInputDialog

        self.setup_dialog()
        for title in ("Barbarian", "Shadow of the Beast", "new"):
            with self.subTest(title=title):
                dialog = SimpleTextInputDialog(
                    self.dialog, "Enter Game Name", "Game Name:",
                    default_text=title,
                )
                self.assertEqual(dialog.text_field.get_text(), title)
                self.assertEqual(dialog.text_field.selectedText(), title)
                dialog.reject()
                dialog.deleteLater()
                self.application.sendPostedEvents(None, QEvent.DeferredDelete)
        self.run_dialog()

    def test_netplay_action_transitions(self):
        from launcher.netplay.irc import LOBBY_CHANNEL
        from launcher.netplay.netplay_panel import NetplayPanel

        with patch("launcher.netplay.netplay_panel.Netplay") as netplay_class:
            netplay = netplay_class.return_value
            netplay.is_op.return_value = True
            netplay.irc.channel.return_value.get_nick_list.return_value = []
            netplay.irc.client.host = "127.0.0.1"
            window = fsui.Window(None, title="Netplay test")
            window.layout = fsui.VerticalLayout()
            panel = NetplayPanel(window, header=False)
            window.layout.add(panel, fill=True, expand=True)
            self.assertFalse(hasattr(panel, "reset_button"))
            self.assertTrue(panel.host_game_button.explicitly_hidden())
            self.assertTrue(panel.start_button.explicitly_hidden())
            window.set_size((800, 600))
            window.show()
            self.application.processEvents()
            try:
                panel.set_active_channel("#test-game")
                self.application.processEvents()
                previous = None
                for control in (
                    panel.host_game_button,
                    panel.start_button, panel.recheck_button,
                ):
                    self.assertTrue(control.visible())
                    geometry = control.widget().geometry()
                    self.assertGreater(geometry.y(), 0)
                    self.assertLessEqual(geometry.right(), panel.size()[0])
                    if previous is not None:
                        self.assertFalse(previous.intersects(geometry))
                    previous = geometry
                panel.host_game_button.widget().click()
                netplay.handle_command.assert_called_with(
                    "/hostgame 127.0.0.1:25101 2"
                )
                # With no game yet, Start and Re-check have nothing to do.
                self.assertFalse(panel.start_button.widget().isEnabled())
                self.assertFalse(panel.recheck_button.widget().isEnabled())
                session = Mock(
                    is_host=True, game_id="4d5211d9-2761", state="configuring",
                    can_start=False,
                )
                session.slot_lines.return_value = [
                    "1. HST (you) \u2014 ready", "2. PL2 \u2014 missing: floppy_drive_0",
                ]
                session.waiting_on.return_value = ["PL2 is missing"]
                panel.on_session(session)
                self.assertEqual(panel.session_list.get_item_count(), 2)
                self.assertFalse(panel.start_button.widget().isEnabled())
                self.assertIn("PL2 is missing", panel.start_button.widget().toolTip())
                # Ready, but with an edit the lobby doesn't have yet.
                session.state = "ready"
                session.waiting_on.return_value = [
                    "your config changes are still being sent"
                ]
                panel.on_session(session)
                self.assertFalse(panel.start_button.widget().isEnabled())
                self.assertIn(
                    "still being sent", panel.start_button.widget().toolTip()
                )
                session.can_start = True
                panel.on_session(session)
                self.assertTrue(panel.start_button.widget().isEnabled())
                panel.recheck_button.widget().click()
                netplay.handle_command.assert_called_with("/recheck")
                with patch("launcher.launcherapp.LauncherApp.start_game") as start:
                    panel.start_button.widget().click()
                    start.assert_called_once_with()
                netplay.is_op.return_value = False
                panel.on_irc("nick_list", {"channel": "#test-game"})
                self.assertFalse(panel.host_game_button.visible())
                self.assertTrue(panel.recheck_button.visible())
                self.assertGreater(panel.recheck_button.widget().geometry().y(), 0)
                panel.set_active_channel(LOBBY_CHANNEL)
                self.assertFalse(panel.recheck_button.visible())
                self.assertFalse(panel.host_game_button.visible())
            finally:
                window.close()


class TestDashboard(WidgetTestCase):
    def test_aligned_settings_preserve_values_and_defaults(self):
        from launcher.option import Option
        from launcher.settings.settings_page import SettingsPage

        self.setup_dialog()
        with patch("launcher.settings.option_ui.LauncherSettings.get", return_value=""):
            with patch("launcher.settings.option_ui.app", Mock(qapplication=self.application)):
                with patch("launcher.settings.option_ui.OverrideWarning", side_effect=lambda parent, name: fsui.Label(parent, "")):
                    page = SettingsPage(self.dialog)
                    text_group = page.add_option("irc_nick")
                    choice_group = page.add_option(Option.LOW_LATENCY_VSYNC)
                    integer_group = page.add_option(Option.LAUNCHER_FONT_SIZE)
        with patch("launcher.settings.option_ui.LauncherSettings.set") as set_value:
            text_group.value_control.set_text("  Player  ")
            set_value.reset_mock()
            text_group.value_control.on_changed()
            set_value.assert_called_once_with("irc_nick", "Player")
            choice_group.value_control.set_index(1)
            set_value.reset_mock()
            choice_group.value_control.on_changed()
            set_value.assert_called_once_with(Option.LOW_LATENCY_VSYNC, "1")
            self.assertFalse(integer_group.value_control.is_enabled())
            integer_group.default_checkbox.check(False)
            self.assertTrue(integer_group.value_control.is_enabled())
            integer_group.value_control.set_value(14)
            set_value.reset_mock()
            integer_group.value_control.on_changed()
            set_value.assert_called_once_with(Option.LAUNCHER_FONT_SIZE, "14")
            integer_group.default_checkbox.check()
            self.assertFalse(integer_group.value_control.is_enabled())
            self.assertEqual(integer_group.value_control.get_value(), Option.get(Option.LAUNCHER_FONT_SIZE)["default"])
            self.assertEqual(set_value.call_args.args, (Option.LAUNCHER_FONT_SIZE, ""))
        with patch("launcher.settings.settings_page.LauncherSettings.set") as reset:
            page.reset_to_defaults()
            self.assertEqual(
                {call.args for call in reset.call_args_list},
                {("irc_nick", ""), (Option.LOW_LATENCY_VSYNC, ""),
                 (Option.LAUNCHER_FONT_SIZE, "")},
            )
        self.run_dialog()

    def test_expanding_options_preserve_overrides(self):
        from launcher.option import Option
        from launcher.ui.options import ConfigWidgetFactory

        self.setup_dialog()
        factory = ConfigWidgetFactory(expand=True)
        options = Mock()
        options.get.return_value = ""
        factory.options = options
        with patch("launcher.ui.options.OptionsBehavior"):
            for key in (Option.JIT_COMPILER, Option.FLOPPY_DRIVE_SPEED,
                        Option.FLOPPY_DRIVE_VOLUME_EMPTY):
                with self.subTest(option=key):
                    group = factory.create(self.dialog, key)
                    checkbox = group.option_label
                    control = group.layout.children[-1].element
                    control.on_explicit_option("")
                    self.assertFalse(control.is_enabled())
                    checkbox.check()
                    options.set.reset_mock()
                    checkbox.on_changed()
                    value = Option.get(key)["default"]
                    options.set.assert_called_once_with(key, value)
                    control.on_explicit_option(value)
                    self.assertTrue(control.is_enabled())
                    if hasattr(control, "choice_values"):
                        control.set_index(1)
                        expected = control.choice_values[1]
                    else:
                        control.set_value(30)
                        expected = "30"
                    options.set.reset_mock()
                    control.on_changed()
                    options.set.assert_called_once_with(key, expected)
                    checkbox.check(False)
                    options.set.reset_mock()
                    checkbox.on_changed()
                    options.set.assert_called_once_with(key, "")
        self.run_dialog()

    def test_configuration_form_control_widths(self):
        from fsui.qt import QComboBox, QSpinBox
        from fsui.qt.modern_theme import apply_modern_theme
        from fsui.qt.retro_theme import apply_retro_theme
        from launcher.panels.additionalconfigpanel import AdditionalConfigPanel
        from launcher.panels.expansionspanel import ExpansionsPanel
        from launcher.panels.romrampanel import RomRamPanel

        palette = self.application.palette()
        stylesheet = self.application.styleSheet()
        font = self.application.font()
        try:
            for variant in ("modern", "plain", "windows311", "workbench"):
                self.application.setStyleSheet("")
                self.application.setPalette(self.application.style().standardPalette())
                self.application.setFont(font)
                if variant == "modern":
                    apply_modern_theme(self.application)
                elif variant != "plain":
                    apply_retro_theme(self.application, variant)
                for panel_type in (RomRamPanel, ExpansionsPanel, AdditionalConfigPanel):
                    with self.subTest(theme=variant, panel=panel_type.__name__), patch.object(fsui, "theme_variant", variant):
                        self.setup_dialog()
                        self.dialog.layout = fsui.VerticalLayout()
                        panel = panel_type(self.dialog)
                        self.dialog.layout.add(panel, fill=True, expand=True)
                        self.dialog.show()
                        try:
                            for width in (540, 900, 1500):
                                with self.subTest(width=width):
                                    self.dialog.set_size((width, 700))
                                    self.application.processEvents()
                                    group = panel.memory_group if isinstance(panel, RomRamPanel) else panel
                                    choices = group.widget().findChildren(QComboBox)
                                    self.assertGreater(len(choices), 1)
                                    widths = [choice.width() for choice in choices]
                                    self.assertLessEqual(max(widths) - min(widths), 1)
                                    self.assertGreater(min(widths), 75)
                                    controls = choices + group.widget().findChildren(QSpinBox)
                                    for control in controls:
                                        self.assertEqual(control.width(), choices[0].width())
                                        self.assertGreaterEqual(control.x(), 0)
                                        self.assertLessEqual(control.geometry().right(), control.parentWidget().width())
                                        checkbox = control.parentWidget().findChild(fsui.qt.QCheckBox)
                                        self.assertGreaterEqual(control.x() - checkbox.geometry().right() - 1, 20)
                                    if isinstance(panel, RomRamPanel):
                                        roms = panel.kickstart_group
                                        self.assertEqual(roms.text_field.x(), roms.ext_text_field.x())
                                        self.assertEqual(roms.kickstart_type_choice.width(), roms.ext_rom_type_choice.width())
                        finally:
                            self.run_dialog()
        finally:
            self.application.setPalette(palette)
            self.application.setStyleSheet(stylesheet)
            self.application.setFont(font)

    def test_restart_button_confirmation(self):
        from fsui.qt import QMessageBox
        from launcher.settings.launchersettingspage import LauncherSettingsPage

        self.setup_dialog()
        application = Mock(qapplication=self.application)
        with patch("launcher.settings.option_ui.app", application):
            with patch("launcher.settings.launchersettingspage.app", application):
                page = LauncherSettingsPage(self.dialog)
                self.assertFalse(page.restart_button.widget().icon().isNull())
                with patch("fsui.qt.QMessageBox.question", return_value=QMessageBox.No):
                    page.restart_button.widget().click()
                    application.request_restart.assert_not_called()
                with patch("fsui.qt.QMessageBox.question", return_value=QMessageBox.Yes):
                    page.restart_button.widget().click()
                    application.request_restart.assert_called_once_with()
                application.request_restart.side_effect = OSError("Disk full")
                with patch("fsui.qt.QMessageBox.question", return_value=QMessageBox.Yes):
                    with patch("fsui.show_error") as show_error:
                        page.restart_button.widget().click()
                        show_error.assert_called_once()
        self.run_dialog()

    def test_portable_mode_confirmation_and_cancellation(self):
        from fsui.qt import QMessageBox
        from launcher.settings.launchersettingspage import LauncherSettingsPage

        self.setup_dialog()
        application = Mock(qapplication=self.application)
        with patch("launcher.settings.option_ui.app", application), \
                patch("launcher.settings.launchersettingspage.app", application), \
                patch("fsboot.is_portable", return_value=False), \
                patch("launcher.portable.PortableModeChange") as change_class, \
                patch("launcher.scanner.Scanner.running", False):
            page = LauncherSettingsPage(self.dialog)
            self.assertFalse(page.portable_checkbox.is_checked())
            self.assertFalse(page.portable_folder_button.is_enabled())
            with patch("fsui.pick_directory", return_value=""):
                page.portable_checkbox.click()
            application.request_restart.assert_not_called()
            self.assertFalse(page.portable_checkbox.is_checked())
            with patch("fsui.pick_directory", return_value="/example/portable"):
                with patch("fsui.qt.QMessageBox.question", return_value=QMessageBox.No):
                    page.portable_checkbox.click()
                application.request_restart.assert_not_called()
                with patch("fsui.qt.QMessageBox.question", return_value=QMessageBox.Yes):
                    page.portable_checkbox.click()
                application.request_restart.assert_called_once_with(
                    portable_change=change_class.return_value
                )
            self.assertFalse(page.portable_checkbox.is_checked())
            application.request_restart.reset_mock()
            with patch("fsboot.is_portable", return_value=True):
                page.reset_portable_checkbox()
                with patch("fsui.pick_directory", return_value="/example/normal"), \
                        patch("fsui.qt.QMessageBox.question", return_value=QMessageBox.Yes):
                    page.portable_checkbox.click()
                self.assertTrue(page.portable_checkbox.is_checked())
                self.assertFalse(change_class.call_args.args[3])
                application.request_restart.assert_called_once_with(
                    portable_change=change_class.return_value
                )
        self.run_dialog()

    def test_workspace_settings_navigation(self):
        from fsui.qt.modern_theme import apply_modern_theme
        from fsui.qt.retro_theme import apply_retro_theme

        palette = self.application.palette()
        stylesheet = self.application.styleSheet()
        font = self.application.font()
        try:
            for variant in ("modern", "plain", "windows311", "workbench"):
                with self.subTest(variant=variant), patch.object(fsui, "theme_variant", variant):
                    if variant == "modern":
                        apply_modern_theme(self.application)
                    elif variant == "plain":
                        self.application.setStyleSheet("")
                        self.application.setPalette(self.application.style().standardPalette())
                    else:
                        apply_retro_theme(self.application, variant)
                    self._check_workspace_settings_navigation()
        finally:
            self.application.setPalette(palette)
            self.application.setStyleSheet(stylesheet)
            self.application.setFont(font)

    def _check_workspace_settings_navigation(self):
        import qtawesome as qta
        from fsui.qt import QEvent
        from launcher.settings.settings_dialog import SettingsDialog

        with patch("qtawesome.icon", wraps=qta.icon) as icons, patch(
            "launcher.settings.option_ui.app", Mock(qapplication=self.application)
        ):
            with patch("launcher.settings.settings_dialog.LauncherSettings.set"):
                with patch("launcher.settings.settings_dialog.LauncherSignal.broadcast"):
                    window = SettingsDialog(None)
                    try:
                        window.show()
                        for title in ("WHDLoad", "Audio", "Keyboard", "WHDLoad"):
                            index = window.set_page_by_title(title)
                            self.application.processEvents()
                            self.assertEqual(window.get_index(), index)
                            self.assertIs(window.page, window.pages[index])
                            self.assertFalse(window.page.widget().isHidden())
                            self.assertIsNone(window.page.icon_header.image_view)
                            self.assertEqual(
                                window.page.icon_header.title_label.font().pixelSize(),
                                25,
                            )
                        for index in range(len(window.pages)):
                            item = window.list_view.model().item(index)
                            self.assertFalse(item.icon().isNull())
                            expected_height = 42 if fsui.theme_variant == "modern" else 44
                            self.assertEqual(item.sizeHint().height(), expected_height)
                        for width in (1000, 1280):
                            window.set_size((width, 760))
                            for index in range(len(window.pages)):
                                title = window.get_page_title(index)
                                with self.subTest(theme=fsui.theme_variant, page=title, width=width):
                                    window.set_page_by_title(title)
                                    self.application.processEvents()
                                    groups = getattr(window.page, "option_groups", [])
                                    fields = []
                                    help_positions = []
                                    for group in groups:
                                        control = group.value_control
                                        control = getattr(control, "_widget", control)
                                        self.assertGreater(control.width(), 60)
                                        self.assertLessEqual(control.geometry().right(), control.parentWidget().width())
                                        help_button = group.help_button.widget()
                                        self.assertLess(control.geometry().right(), help_button.x())
                                        help_positions.append(help_button.x())
                                        if not hasattr(group, "default_checkbox"):
                                            fields.append((control.x(), control.width()))
                                        if hasattr(group, "label_layout"):
                                            self.assertGreaterEqual(control.x() - group.label_layout.get_min_width(), 20)
                                    self.assertLessEqual(len(set(fields)), 1)
                                    self.assertLessEqual(len(set(help_positions)), 1)
                        colors = {
                            "modern": "#9bcce2", "windows311": "#183867",
                            "workbench": "#0055aa", "plain": "#000000",
                        }
                        icons.assert_any_call("fa5s.globe", color=colors[fsui.theme_variant])
                        icons.assert_any_call("fa5s.hdd", color=colors[fsui.theme_variant])
                        if fsui.theme_variant != "modern":
                            self.assertEqual(window.list_view.iconSize().width(), 20 if fsui.theme_variant == "plain" else 24)
                            self.assertIn("palette(highlight)", window.list_view.styleSheet())
                            self.assertNotIn("#1c1e2b", window.list_view.styleSheet())
                    finally:
                        window.close()
                        window.real_window().deleteLater()
                        self.application.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_modern_theme_option(self):
        from launcher.option import Option
        from launcher.settings.option_ui import OptionUI

        self.setup_dialog()
        with patch("launcher.settings.option_ui.LauncherSettings.get", return_value=""):
            group = OptionUI.create_group(
                self.dialog, Option.LAUNCHER_THEME, help_button=False
            )
        labels = [group.widget.itemText(index) for index in range(group.widget.count())]
        self.assertIn("Modern Dark", labels)
        self.assertEqual(labels[0], "Modern Dark (*)")
        self.assertEqual(labels.count("Windows 3.11"), 1)
        self.assertEqual(labels.count("Amiga Workbench 1.3"), 1)
        self.assertEqual(labels, [
            "Modern Dark (*)", "Modern Dark", "Fusion", "Windows 3.11", "Amiga Workbench 1.3"
        ])
        self.run_dialog()

    def test_navigation_and_responsive_layout(self):
        from fsui.qt.modern_theme import apply_modern_theme
        from fsui.qt.retro_theme import apply_retro_theme

        palette = self.application.palette()
        stylesheet = self.application.styleSheet()
        font = self.application.font()
        try:
            for variant in ("modern", "plain", "windows311", "workbench"):
                with self.subTest(variant=variant):
                    with patch.object(fsui, "theme_variant", variant):
                        if variant == "modern":
                            apply_modern_theme(self.application)
                        elif variant == "plain":
                            self.application.setStyleSheet("")
                            self.application.setPalette(self.application.style().standardPalette())
                        else:
                            apply_retro_theme(self.application, variant)
                        self._check_navigation_and_responsive_layout()
        finally:
            self.application.setPalette(palette)
            self.application.setStyleSheet(stylesheet)
            self.application.setFont(font)

    def _check_navigation_and_responsive_layout(self):
        from launcher.ui.book import Book
        from launcher.ui.dashboard import Dashboard

        owner = fsui.Window(None, title="Dashboard test")
        owner.gsc = object()
        owner.books = [None, Book(owner), Book(owner)]
        owner.books[1].add_page(fsui.Panel(owner.books[1]))
        owner.books[1].set_page(0)
        for index in range(8):
            panel = fsui.Panel(owner.books[2])
            panel.layout = fsui.VerticalLayout()
            panel.layout.add_spacer(400, 200)
            owner.books[2].add_page(panel)
        owner.screenshots_panel = fsui.Panel(owner)
        owner.game_info_panel = fsui.Panel(owner)
        owner.quick_settings_panel = fsui.Panel(owner)
        owner.status_bar = fsui.Panel(owner)
        owner.on_net_play = Mock()
        owner.on_settings_button = Mock()

        def create_launch_group(parent, context):
            group = fsui.Group(parent)
            group.layout = fsui.VerticalLayout()
            group.layout.add(fsui.Button(group, "Start"), fill=True)
            return group

        with patch("launcher.ui.dashboard.LaunchGroup", create_launch_group):
            with patch("launcher.ui.dashboard.LauncherSettings") as settings:
                settings.get.return_value = "Test configuration"
                dashboard = Dashboard(owner)
                owner.layout = fsui.VerticalLayout()
                owner.layout.add(dashboard, fill=True, expand=True)
                owner.show()
                for size in ((1920, 1080), (1280, 800), (1000, 720)):
                    owner.set_size(size)
                    self.application.processEvents()
                    for index, button in enumerate(dashboard.nav_buttons):
                        button.click()
                        self.assertIs(
                            owner.books[2].current_page,
                            owner.books[2].pages[index],
                        )
                        self.assertTrue(button.isChecked())
                    self.assertLessEqual(dashboard.widget().width(), size[0])
                    self.assertLessEqual(dashboard.widget().height(), size[1])
                    self.assertEqual(dashboard.media.isHidden(), size[1] < 820)
                    dashboard.quick_toggle.click()
                    self.application.processEvents()
                    self.assertEqual(dashboard.library.isHidden(), size[0] < 1400)
                    self.assertLessEqual(dashboard.widget().width(), size[0])
                    dashboard.quick_toggle.click()
                    self.assertFalse(dashboard.library.isHidden())
                dashboard.library_toggle.click()
                self.assertTrue(dashboard.library.isHidden())
                dashboard.library_toggle.click()
                self.assertFalse(dashboard.library.isHidden())
                dashboard.quick_toggle.click()
                self.assertFalse(dashboard.quick_area.isHidden())
                dashboard.quick_toggle.click()
                self.assertTrue(dashboard.quick_area.isHidden())
                with patch("launcher.netplay.irc.IRC.connect") as connect:
                    with patch("launcher.netplay.netplay.ConnectionTester"):
                        dashboard.netplay_button.click()
                        page = dashboard.netplay_page
                        self.assertIs(dashboard.content_stack.currentWidget(), page.widget())
                        self.assertIs(page.server_details.window(), owner.real_window())
                        if fsui.theme_variant != "modern":
                            self.assertNotIn("#212431", page.server_details.styleSheet())
                            self.assertNotIn("#171923", dashboard.widget().styleSheet())
                        self.assertTrue(dashboard.netplay_button.isChecked())
                        self.assertTrue(dashboard.launch_bar.isHidden())
                        self.assertFalse(dashboard.library_toggle.isEnabled())
                        page.panel.text_area.append_text("Persistent chat")
                        dashboard.nav_buttons[0].click()
                        self.assertIs(dashboard.content_stack.currentWidget(), dashboard.workspace)
                        self.assertFalse(dashboard.launch_bar.isHidden())
                        dashboard.netplay_button.click()
                        self.assertIs(dashboard.netplay_page, page)
                        self.assertIn("Persistent chat", page.panel.text_area.get_text())
                        connect.assert_called_once_with()
                        from launcher.ui.launcherwindow import LauncherWindow

                        owner.dashboard = dashboard
                        with patch("launcher.netplay.netplay_page.NetplayPage") as new_page:
                            LauncherWindow.on_net_play(owner)
                            new_page.assert_not_called()
                        server = Mock(players=2, process=None)
                        page.server_details.present(
                            page.panel, server, "test-id", 25101, "#test-game"
                        )
                        page.panel.netplay.game_window = page.server_details
                        owner.close()
                        server.stop.assert_called_once_with()