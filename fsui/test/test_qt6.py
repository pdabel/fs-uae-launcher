import os
import unittest
from unittest.mock import Mock, call, patch

import fsui
from fsui.qt import (
    QDialog,
    QEvent,
    QFont,
    QFontMetrics,
    QImage,
    QPainter,
    QTimer,
)
from fsui.qt.DrawingContext import DrawingContext
from fsui.qt.qt import configure_qt_environment
from .WidgetTestCase import WidgetTestCase


class TestQtEnvironment(unittest.TestCase):
    def test_gnome_defaults_to_generic_theme(self):
        with patch.dict(
            os.environ, {"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}, clear=True
        ):
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
        with patch.dict(
            os.environ, {"XDG_CURRENT_DESKTOP": "KDE"}, clear=True
        ):
            with patch("sys.platform", "linux"):
                configure_qt_environment()
                self.assertNotIn("QT_QPA_PLATFORMTHEME", os.environ)

    def test_other_platforms_are_unchanged(self):
        for platform in ("win32", "darwin"):
            with self.subTest(platform=platform):
                with patch.dict(
                    os.environ, {"XDG_CURRENT_DESKTOP": "GNOME"}, clear=True
                ):
                    with patch("sys.platform", platform):
                        configure_qt_environment()
                        self.assertNotIn("QT_QPA_PLATFORMTHEME", os.environ)


class TestQt6(WidgetTestCase):
    def test_empty_state_controls_never_show_as_top_level_windows(self):
        from fsui.qt import QApplication, QListView, QObject, QWidget
        from launcher.ui.empty_state import EmptyStateOverlay

        shown_windows = []

        class ShowObserver(QObject):
            def eventFilter(self, watched, event):
                if (
                    event.type() == QEvent.Type.Show
                    and isinstance(watched, QWidget)
                    and watched.isWindow()
                ):
                    shown_windows.append(watched)
                return False

        self.setup_dialog()
        view = QListView(self.dialog)
        observer = ShowObserver()
        application = QApplication.instance()
        application.installEventFilter(observer)
        try:
            for hint, action in (("Hint", "Scan"), ("", "")):
                with self.subTest(hint=hint, action=action):
                    clicked = Mock()
                    overlay = EmptyStateOverlay(
                        view, "No games", hint, action, clicked
                    )
                    self.assertEqual(shown_windows, [])
                    for child in (overlay.title, overlay.hint, overlay.button):
                        self.assertIs(child.parentWidget(), overlay)
                        self.assertFalse(child.isWindow())
                    self.assertEqual(overlay.hint.isHidden(), not bool(hint))
                    self.assertEqual(
                        overlay.button.isHidden(), not bool(action)
                    )
                    overlay.button.click()
                    clicked.assert_called_once()
                    overlay.set_text("No matches", "Try again")
                    self.assertFalse(overlay.hint.isHidden())
                    overlay.set_text("No matches")
                    self.assertTrue(overlay.hint.isHidden())
                    overlay.deleteLater()
        finally:
            application.removeEventFilter(observer)
        self.run_dialog()

    def test_dashboard_focuses_search_before_mapping_window(self):
        from fsui.qt import QWidget
        from launcher.ui.launcherwindow import LauncherWindow

        owner = Mock()
        owner.real_widget.return_value = QWidget()
        owner.real_window.return_value.screen.return_value.availableGeometry.return_value = Mock(
            width=lambda: 1280, height=lambda: 800
        )
        order = Mock()
        order.attach_mock(owner.configurations_panel.text_field.focus, "focus")
        order.attach_mock(owner.maximize, "maximize")
        with patch("launcher.ui.dashboard.Dashboard"):
            LauncherWindow.install_dashboard(owner)
        self.assertEqual(order.mock_calls, [call.focus(), call.maximize()])

    def test_preferred_screen_creates_native_handle_before_show(self):
        from fsui.qt import QWidget
        from launcher.ui.launcherwindow import LauncherWindow

        window = QWidget()
        owner = Mock()
        owner.real_window.return_value = window
        self.assertIsNone(window.windowHandle())
        with patch(
            "launcher.ui.launcherwindow.LauncherSettings.get", return_value=""
        ):
            LauncherWindow.move_to_preferred_screen(owner)
        self.assertIsNotNone(window.windowHandle())
        self.assertIs(
            window.windowHandle().screen(), self.application.primaryScreen()
        )
        self.assertFalse(window.isVisible())
        window.close()

    def test_preferred_screen_targets_saved_display_before_show(self):
        from launcher.ui.launcherwindow import LauncherWindow

        primary = Mock()
        selected = Mock()
        application = Mock()
        application.screens.return_value = [primary, selected]
        application.primaryScreen.return_value = primary
        window = Mock()
        handle = window.windowHandle.return_value
        order = Mock()
        order.attach_mock(window.winId, "create")
        order.attach_mock(handle.setScreen, "set_screen")
        owner = Mock()
        owner.real_window.return_value = window
        with patch("fsui.qt.init_qt", return_value=application), patch(
            "fsgs.displays.screen_index", return_value=1
        ) as lookup, patch(
            "launcher.ui.launcherwindow.LauncherSettings.get",
            return_value="saved",
        ):
            LauncherWindow.move_to_preferred_screen(owner)
        lookup.assert_called_once_with([primary, selected], "saved", primary)
        self.assertEqual(
            order.mock_calls, [call.create(), call.set_screen(selected)]
        )

    def test_screen_info_follows_effective_game_monitor(self):
        from fsbc.signal import Signal
        from launcher.ui.launch import ScreenInfoLabel

        state = {"monitor": "game", "overrides": {"monitor": "game"}}
        settings = {"fullscreen": "1", "monitor": "global"}
        self.setup_dialog()
        with patch(
            "launcher.launcher_config.LauncherConfig.get",
            side_effect=lambda key: state.get(key, ""),
        ), patch(
            "launcher.launcher_config.LauncherConfig.get_game_overrides",
            side_effect=lambda: state["overrides"],
        ), patch(
            "launcher.launcher_settings.LauncherSettings.get",
            side_effect=lambda key: settings.get(key, ""),
        ), patch(
            "launcher.ui.launch.GameDriver.screen_rect_for_monitor",
            side_effect=lambda monitor: (
                0,
                0,
                {"game": 1000, "global": 2000, "": 3000}[monitor],
                800,
            ),
        ), patch(
            "launcher.ui.launch.GameDriver.screen_refresh_rate_for_monitor",
            return_value=60,
        ):
            label = ScreenInfoLabel(self.dialog)
            self.assertIn("1000x800", label.text())
            settings["monitor"] = ""
            label.on_monitor_setting("")
            self.assertIn("1000x800", label.text())
            settings["monitor"] = "global"
            state["monitor"] = ""
            state["overrides"] = {"monitor": ""}
            Signal("fsgs:config").notify("__game_override_context", "")
            self.assertIn("3000x800", label.text())
            state["overrides"] = {}
            Signal("fsgs:config").notify("__game_override_context", "")
            self.assertIn("2000x800", label.text())
            state["monitor"] = "game"
            Signal("fsgs:config").notify("monitor", "game")
            self.assertIn("1000x800", label.text())
        self.run_dialog()

    def test_detected_monitor_choices_persist_and_handle_disconnect(self):
        from types import SimpleNamespace
        from fsui.qt import QRect
        from fsgs.displays import display_id
        from launcher.settings.monitorbutton import MonitorChoice
        from launcher.settings.option_ui import OptionUI

        def display(name, horizontal):
            return SimpleNamespace(
                name=lambda: name,
                manufacturer=lambda: "Test",
                model=lambda: "Test Display",
                serialNumber=lambda: name,
                geometry=lambda: QRect(horizontal, 0, 1920, 1080),
                geometryChanged=Mock(),
            )

        first = display("DP-1", -1920)
        second = display("HDMI-1", 0)
        screens = [first, second]
        application = Mock()
        application.screens.side_effect = lambda: screens
        settings = {"monitor": ""}
        self.setup_dialog()
        with patch(
            "launcher.settings.monitorbutton.init_qt", return_value=application
        ), patch("launcher.settings.monitorbutton.MonitorHighlight"), patch(
            "launcher.settings.monitorbutton.LauncherSettings.get",
            side_effect=lambda key: settings.get(key, ""),
        ), patch(
            "launcher.settings.monitorbutton.LauncherSettings.set",
            side_effect=settings.__setitem__,
        ):
            choice = MonitorChoice(self.dialog)
            group = OptionUI.create_group(
                self.dialog, "monitor", help_button=False
            )
            self.assertIsInstance(group.value_control, MonitorChoice)
            self.assertEqual(choice.count(), 3)
            self.assertIn("DP-1", choice.itemText(1))
            choice.set_index(2)
            self.assertEqual(settings["monitor"], display_id(second))
            group.value_control.on_monitor_setting(settings["monitor"])
            self.assertEqual(
                group.value_control.values[group.value_control.get_index()],
                display_id(second),
            )
            screens[:] = [first]
            choice.refresh()
            self.assertIn("unavailable", choice.currentText())
            self.assertEqual(settings["monitor"], display_id(second))
            screens[:] = [second, first]
            choice.on_screen_added(second)
            self.assertIn("HDMI-1", choice.currentText())
            self.assertEqual(choice.get_index(), 1)
            self.assertEqual(settings["monitor"], display_id(second))
            reconnected = display("HDMI-2", 0)
            reconnected.serialNumber = second.serialNumber
            screens[:] = [first, reconnected]
            choice.refresh()
            self.assertIn("HDMI-2", choice.currentText())
            self.assertNotIn("unavailable", choice.currentText())
            self.assertEqual(choice.get_index(), 2)
            self.assertEqual(settings["monitor"], display_id(second))
            settings["monitor"] = "right"
            choice.refresh()
            self.assertIn("legacy", choice.currentText())
            choice.set_index(0)
            self.assertEqual(settings["monitor"], "")
        self.run_dialog()

    def test_per_game_controls_refresh_when_context_changes(self):
        from fsbc.signal import Signal
        from fsui.qt import QRect
        from fsgs.displays import display_id
        from launcher.settings.monitorbutton import MonitorChoice
        from launcher.settings.option_ui import OptionUI

        def display(name, serial):
            return SimpleNamespace(
                name=lambda: name,
                manufacturer=lambda: "Test",
                model=lambda: "Test Display",
                serialNumber=lambda: serial,
                geometry=lambda: QRect(0, 0, 1920, 1080),
                geometryChanged=Mock(),
            )

        from types import SimpleNamespace

        original = display("HDMI-1", "serial")
        reconnected = display("HDMI-2", "serial")
        ambiguous = display("HDMI-3", "serial")
        screens = [reconnected, ambiguous]
        application = Mock()
        application.screens.side_effect = lambda: screens
        application.primaryScreen.side_effect = lambda: screens[0]
        state = {
            "base": {"scale": "custom-a"},
            "overrides": {"monitor": display_id(original)},
            "available": True,
        }
        self.setup_dialog()
        with patch(
            "launcher.settings.monitorbutton.init_qt", return_value=application
        ), patch(
            "launcher.launcher_config.LauncherConfig.get", return_value=""
        ), patch(
            "launcher.launcher_config.LauncherConfig.game_override_identity",
            return_value=("variant_uuid", "game"),
        ), patch(
            "launcher.launcher_config.LauncherConfig.game_overrides_available",
            side_effect=lambda: state["available"],
        ), patch(
            "launcher.launcher_config.LauncherConfig.get_game_overrides",
            side_effect=lambda: state["overrides"].copy(),
        ), patch(
            "launcher.launcher_config.LauncherConfig.get_game_base_value",
            side_effect=lambda key: state["base"].get(key, ""),
        ), patch(
            "launcher.settings.option_ui.LauncherSettings.get", return_value=""
        ), patch(
            "launcher.settings.monitorbutton.LauncherSettings.get",
            return_value="",
        ):
            monitor = MonitorChoice(self.dialog, per_game=True)
            scale = OptionUI.create_group(
                self.dialog, "scale", help_button=False, per_game=True
            )
            self.assertIn("unavailable", monitor.currentText())
            self.assertEqual(
                monitor.values[monitor.get_index()], display_id(original)
            )
            self.assertIn("custom-a", scale.widget.currentText())
            screens[:] = [reconnected]
            state["base"]["scale"] = "custom-b"
            Signal("fsgs:config").notify("__game_override_context", "")
            self.assertIn("HDMI-2", monitor.currentText())
            self.assertNotIn("unavailable", monitor.currentText())
            self.assertIn("custom-b", scale.widget.currentText())
            state["overrides"] = {}
            state["base"] = {}
            Signal("fsgs:config").notify("__game_override_context", "")
            self.assertIsNone(monitor.values[monitor.get_index()])
            self.assertIn("Default", scale.widget.currentText())
            state["available"] = False
            Signal("fsgs:config").notify("__game_override_context", "")
            self.assertFalse(monitor.isEnabled())
            self.assertFalse(scale.value_control.isEnabled())
            self.assertEqual(
                scale.game_state_label.text(), "Overrides unavailable"
            )
        self.run_dialog()

    def test_monitor_highlight_previews_without_saving_and_times_out(self):
        from fsui.qt import Qt
        from launcher.settings.monitorbutton import (
            MonitorChoice,
            MonitorHighlight,
        )

        self.setup_dialog()
        self.dialog.layout = fsui.VerticalLayout()
        with patch(
            "launcher.settings.monitorbutton.LauncherSettings.get",
            return_value="",
        ), patch(
            "launcher.settings.monitorbutton.LauncherSettings.set"
        ) as save:
            choice = MonitorChoice(self.dialog)
            self.dialog.layout.add(choice, fill=True)
            self.dialog.set_size((540, 300))
            self.dialog.show()
            self.application.processEvents()
            choice.showPopup()
            self.application.processEvents()
            self.assertTrue(choice.view().isVisible())
            focused = self.application.focusWidget()
            choice.on_highlighted(1)
            self.application.processEvents()
            self.assertTrue(choice.view().isVisible())
            self.assertIs(self.application.focusWidget(), focused)
            indicator = choice.monitor_highlight
            self.assertIsInstance(indicator, MonitorHighlight)
            self.assertTrue(indicator.isVisible())
            self.assertIs(indicator.selected, self.application.screens()[0])
            self.assertFalse(indicator.isWindow())
            self.assertFalse(
                indicator.windowState() & Qt.WindowState.WindowFullScreen
            )
            self.assertLessEqual(indicator.width(), 360)
            self.assertLessEqual(indicator.height(), 160)
            self.assertTrue(self.dialog.rect().contains(indicator.geometry()))
            self.assertTrue(
                indicator.testAttribute(
                    Qt.WidgetAttribute.WA_TransparentForMouseEvents
                )
            )
            self.assertTrue(
                indicator.testAttribute(
                    Qt.WidgetAttribute.WA_ShowWithoutActivating
                )
            )
            self.assertEqual(indicator.focusPolicy(), Qt.FocusPolicy.NoFocus)
            self.assertIsNot(
                self.dialog.childAt(indicator.geometry().center()), indicator
            )
            self.assertIn(self.application.screens()[0].name(), indicator.text)
            save.assert_not_called()
            image = indicator.grab().toImage()
            self.assertLessEqual(image.width(), 360)
            self.assertLessEqual(image.height(), 160)
            self.assertTrue(indicator.monitor_rects())
            choice.hidePopup()
            self.assertFalse(indicator.isVisible())
            choice.on_monitor_activated(1)
            self.assertTrue(indicator.isVisible())
            self.assertEqual(indicator.timer.interval(), 1800)
            self.assertTrue(indicator.timer.isActive())
            choice.hidePopup()
            self.assertTrue(indicator.isVisible())
            indicator.timer.timeout.emit()
            self.assertFalse(indicator.isVisible())
            choice.on_highlighted(1)
            choice.refresh()
            self.assertFalse(indicator.isVisible())
            save.assert_not_called()
        self.run_dialog()

    def test_monitor_preview_diagram_preserves_layout_and_stays_bounded(self):
        from types import SimpleNamespace
        from fsui.qt import QRect
        from launcher.settings.monitorbutton import MonitorHighlight

        self.setup_dialog()
        preview = MonitorHighlight(self.dialog)
        preview.resize(360, 160)
        left = SimpleNamespace(
            geometry=lambda: QRect(-1920, 0, 1920, 1080), name=lambda: "DP-1"
        )
        upper = SimpleNamespace(
            geometry=lambda: QRect(0, -1080, 1920, 1080), name=lambda: "HDMI-1"
        )
        preview.screens = [left, upper]
        preview.selected = upper
        rectangles = preview.monitor_rects()
        self.assertEqual(len(rectangles), 2)
        for screen, rect in rectangles:
            self.assertTrue(preview.rect().contains(rect))
        self.assertLess(
            rectangles[0][1].center().x(), rectangles[1][1].center().x()
        )
        self.assertGreater(
            rectangles[0][1].center().y(), rectangles[1][1].center().y()
        )
        image = preview.grab().toImage()
        selected_rect = rectangles[1][1]
        self.assertGreater(
            image.pixelColor(
                selected_rect.left(), selected_rect.center().y()
            ).blue(),
            180,
        )
        self.run_dialog()

    def test_cpu_performance_confirmation_and_restore(self):
        from fsui.qt import QMessageBox
        from launcher.cpu_performance import CpuPolicy
        from launcher.settings.cpu_performance_group import CPUPerformanceGroup

        original = (
            CpuPolicy(
                "policy0", "powersave", ("powersave", "performance"), (0, 1)
            ),
        )
        performance = (
            CpuPolicy(
                "policy0", "performance", ("powersave", "performance"), (0, 1)
            ),
        )
        self.setup_dialog()
        with patch(
            "launcher.settings.cpu_performance_group.read_policies",
            return_value=original,
        ) as read, patch(
            "launcher.settings.cpu_performance_group.QProcess"
        ) as process_class, patch(
            "launcher.cpu_performance.shutil.which",
            side_effect=lambda name: "/usr/bin/" + name,
        ):
            group = CPUPerformanceGroup(self.dialog)
            self.assertTrue(group.performance_button.is_enabled())
            self.assertFalse(group.restore_button.is_enabled())
            with patch(
                "fsui.qt.QMessageBox.question",
                return_value=QMessageBox.StandardButton.No,
            ):
                group.performance_button.widget().click()
            process_class.return_value.start.assert_not_called()
            self.assertIsNone(group.previous)
            with patch(
                "fsui.qt.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ):
                group.performance_button.widget().click()
            process_class.return_value.start.assert_called_once_with(
                "/usr/bin/pkexec",
                [
                    "--disable-internal-agent",
                    "/usr/bin/cpupower",
                    "--cpu",
                    "0,1",
                    "frequency-set",
                    "--governor",
                    "performance",
                ],
            )
            self.assertTrue(group.busy)
            self.assertFalse(group.restore_button.is_enabled())
            read.return_value = performance
            group.on_process_finished(0, process_class.ExitStatus.NormalExit)
            self.assertFalse(group.busy)
            self.assertTrue(group.restore_button.is_enabled())
            self.assertFalse(group.performance_button.is_enabled())
            self.assertEqual(group.previous, original)
            with patch(
                "fsui.qt.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ):
                group.restore_button.widget().click()
            self.assertEqual(
                process_class.return_value.start.call_args.args[1][-1],
                "powersave",
            )
            read.return_value = original
            group.on_process_finished(0, process_class.ExitStatus.NormalExit)
            self.assertIsNone(group.previous)
            self.assertTrue(group.performance_button.is_enabled())
        self.run_dialog()

    def test_cpu_performance_denial_retains_restore_snapshot(self):
        from fsui.qt import QMessageBox
        from launcher.cpu_performance import CpuPolicy
        from launcher.settings.cpu_performance_group import CPUPerformanceGroup

        original = (
            CpuPolicy(
                "policy0", "powersave", ("powersave", "performance"), (0,)
            ),
        )
        self.setup_dialog()
        with patch(
            "launcher.settings.cpu_performance_group.read_policies",
            return_value=original,
        ), patch(
            "launcher.settings.cpu_performance_group.QProcess"
        ) as process_class, patch(
            "launcher.cpu_performance.shutil.which",
            side_effect=lambda name: "/usr/bin/" + name,
        ), patch(
            "fsui.show_error"
        ) as error:
            process_class.return_value.readAllStandardError.return_value = (
                b"Not authorized"
            )
            group = CPUPerformanceGroup(self.dialog)
            with patch(
                "fsui.qt.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ):
                group.performance_button.widget().click()
            group.on_process_finished(126, process_class.ExitStatus.NormalExit)
            error.assert_called_once()
            self.assertFalse(group.busy)
            self.assertEqual(group.previous, original)
            self.assertTrue(group.restore_button.is_enabled())
        self.run_dialog()

    def test_cpu_performance_reports_missing_tools_and_cpu_controls(self):
        from launcher.cpu_performance import CpuPolicy
        from launcher.settings.cpu_performance_group import CPUPerformanceGroup

        original = (
            CpuPolicy(
                "policy0", "powersave", ("powersave", "performance"), (0,)
            ),
        )
        self.setup_dialog()
        with patch(
            "launcher.settings.cpu_performance_group.read_policies",
            return_value=original,
        ) as read, patch(
            "launcher.settings.cpu_performance_group.QProcess"
        ) as process_class, patch(
            "launcher.cpu_performance.shutil.which", return_value=None
        ):
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

        original = (
            CpuPolicy(
                "policy0", "powersave", ("powersave", "performance"), (0,)
            ),
        )
        self.setup_dialog()
        with patch(
            "launcher.settings.cpu_performance_group.read_policies",
            return_value=original,
        ), patch(
            "launcher.settings.cpu_performance_group.QProcess"
        ) as process_class, patch(
            "launcher.cpu_performance.shutil.which",
            side_effect=lambda name: "/usr/bin/" + name,
        ), patch(
            "fsui.qt.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ), patch(
            "fsui.show_error"
        ) as error:
            group = CPUPerformanceGroup(self.dialog)
            group.performance_button.widget().click()
            group.on_process_finished(0, process_class.ExitStatus.NormalExit)
            self.assertIn("not applied", error.call_args.args[0])
            self.assertEqual(group.previous, original)
            error.reset_mock()
            group.performance_button.widget().click()
            group.on_timeout()
            process_class.return_value.kill.assert_called_once()
            group.on_process_error(process_class.ProcessError.Crashed)
            self.assertTrue(group.busy)
            error.assert_not_called()
            group.on_process_finished(9, process_class.ExitStatus.CrashExit)
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
                self.application.palette()
                .color(QPalette.ColorRole.Window)
                .name(),
                "#171923",
            )
            self.assertGreater(
                self.application.palette()
                .color(QPalette.ColorRole.Text)
                .lightness(),
                self.application.palette()
                .color(QPalette.ColorRole.Base)
                .lightness(),
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
        icon = QImage(16, 16, QImage.Format.Format_ARGB32)
        icon.fill(QColor("#ff8800"))
        warning.icons = [fsui.Image(object=icon)]
        image = QImage(320, 40, QImage.Format.Format_ARGB32)
        image.fill(QColor("#171923"))
        painter = QPainter(image)
        try:
            context = DrawingContext(painter)
            with patch(
                "launcher.ui.statusbar.StatusBar.StatusBar.draw_element_background"
            ):
                for element in (status, warning):
                    for color in ("#edf0f7", "#123456"):
                        with self.subTest(
                            element=type(element).__name__, color=color
                        ):
                            palette = element.widget().palette()
                            palette.setColor(
                                QPalette.ColorRole.WindowText, QColor(color)
                            )
                            element.widget().setPalette(palette)
                            with patch.object(
                                element, "create_dc", return_value=context
                            ):
                                with patch.object(
                                    context,
                                    "draw_text",
                                    wraps=context.draw_text,
                                ) as draw_text:
                                    element.on_paint()
                                    draw_text.assert_called_once()
                            self.assertEqual(
                                context.get_text_color(), QColor(color)
                            )
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
            for windows, macosx in (
                (True, False),
                (False, True),
                (False, False),
            ):
                with self.subTest(
                    variant=variant, windows=windows, macosx=macosx
                ):
                    with patch.object(fsui, "theme_variant", variant):
                        with patch("fsbc.system.windows", windows), patch(
                            "fsbc.system.macosx", macosx
                        ):
                            with patch(
                                "launcher.ui.skin.LauncherSettings.get",
                                return_value="",
                            ):
                                self.assertIsNone(
                                    Skin._get_background_color.__wrapped__(
                                        Skin
                                    )
                                )
                            with patch(
                                "launcher.ui.skin.LauncherSettings.get",
                                return_value="#314159",
                            ):
                                self.assertEqual(
                                    Skin._get_background_color.__wrapped__(
                                        Skin
                                    ).name(),
                                    "#314159",
                                )

    def test_modern_control_assets_and_interaction(self):
        from pathlib import Path
        from fsui.qt import QCheckBox, QComboBox, QIcon, QSpinBox
        from fsui.qt import modern_theme

        for name in ("check", "chevron-up", "chevron-down", "retro-chevron"):
            icon = QIcon(
                str(
                    Path(modern_theme.__file__).parent
                    / "res"
                    / (name + ".svg")
                )
            )
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

    def test_numeric_fields_align_with_dropdowns_across_modern_skins(self):
        from fsui.qt import (
            QComboBox,
            QSignalBlocker,
            QStyle,
            QStyleOptionComboBox,
            QStyleOptionFrame,
            modern_theme,
        )
        from fsui.qt.qt import apply_launcher_theme

        palette = self.application.palette()
        stylesheet = self.application.styleSheet()
        font = self.application.font()
        state = fsui.theme, fsui.theme_variant, fsui.theme_skin
        self.setup_dialog()
        spin = fsui.SpinCtrl(self.dialog, 0, 100, 25)
        choice = QComboBox(self.dialog.get_container())
        choice.addItem("25")
        spin.widget().show()
        choice.show()
        try:
            for theme in [
                *("fusion-" + skin for skin in modern_theme.SKINS),
                "fusion-plain",
                "fusion-windows311",
                "fusion-workbench",
                "fusion-cyberpunk",
            ]:
                with self.subTest(theme=theme):
                    apply_launcher_theme(self.application, theme)
                    for enabled in (True, False):
                        spin.widget().setEnabled(enabled)
                        choice.setEnabled(enabled)
                        for width in (160, 400):
                            spin.widget().resize(width, 50)
                            choice.resize(width, 50)
                            self.application.processEvents()
                            editor = spin.widget().lineEdit()
                            option = QStyleOptionFrame()
                            option.initFrom(spin.widget())
                            contents = (
                                spin.widget()
                                .style()
                                .subElementRect(
                                    QStyle.SubElement.SE_LineEditContents,
                                    option,
                                    spin.widget(),
                                )
                            )
                            self.assertGreaterEqual(
                                editor.x(), max(0, contents.x() - 2)
                            )
                            if fsui.theme_variant == "modern":
                                combo_option = QStyleOptionComboBox()
                                choice.initStyleOption(combo_option)
                                combo_contents = choice.style().subControlRect(
                                    QStyle.ComplexControl.CC_ComboBox,
                                    combo_option,
                                    QStyle.SubControl.SC_ComboBoxEditField,
                                    choice,
                                )
                                self.assertEqual(
                                    editor.x() + 2, combo_contents.x()
                                )
                                if enabled and width == 400:
                                    editor.deselect()
                                    text_positions = []
                                    for control in (spin.widget(), choice):
                                        image = QImage(
                                            control.size(),
                                            QImage.Format.Format_ARGB32,
                                        )
                                        image.fill(0)
                                        control.render(image)
                                        # Compare with blank text so antialiased
                                        # glyphs need not contain a solid pixel.
                                        blank = QImage(
                                            image.size(), image.format()
                                        )
                                        blank.fill(0)
                                        with QSignalBlocker(
                                            spin.widget()
                                        ), QSignalBlocker(editor):
                                            if control is spin.widget():
                                                text = editor.text()
                                                editor.setText("")
                                                control.render(blank)
                                                editor.setText(text)
                                            else:
                                                text = choice.itemText(0)
                                                choice.setItemText(0, "")
                                                control.render(blank)
                                                choice.setItemText(0, text)
                                        text_pixels = [
                                            x
                                            for x in range(2, 100)
                                            for y in range(10, 40)
                                            if image.pixel(x, y)
                                            != blank.pixel(x, y)
                                        ]
                                        self.assertTrue(
                                            text_pixels,
                                            (theme, type(control).__name__),
                                        )
                                        text_positions.append(min(text_pixels))
                                    self.assertLessEqual(
                                        abs(
                                            text_positions[0]
                                            - text_positions[1]
                                        ),
                                        1,
                                    )
                            self.assertGreater(editor.width(), 0)
                    spin.widget().setEnabled(True)
                    spin.widget().stepUp()
                    self.assertEqual(spin.get_value(), 26)
                    spin.set_value(25)
        finally:
            choice.deleteLater()
            self.run_dialog()
            modern_theme.apply_modern_theme(self.application, "modern")
            self.application.setPalette(palette)
            self.application.setStyleSheet(stylesheet)
            self.application.setFont(font)
            fsui.theme, fsui.theme_variant, fsui.theme_skin = state

    def test_navigation_icon_variants(self):
        from fsui.qt import QIcon, QSize
        from launcher.ui.navigation_icons import navigation_icon

        images = {}
        for variant in ("modern", "plain", "windows311", "workbench"):
            with self.subTest(variant=variant), patch.object(
                fsui, "theme_variant", variant
            ):
                icon = navigation_icon("fa5s.save")
                self.assertFalse(icon.isNull())
                for extent in (20, 24, 48):
                    for mode in (
                        QIcon.Mode.Normal,
                        QIcon.Mode.Selected,
                        QIcon.Mode.Disabled,
                    ):
                        image = icon.pixmap(
                            QSize(extent, extent), mode
                        ).toImage()
                        self.assertEqual(image.size(), QSize(extent, extent))
                        self.assertTrue(
                            any(
                                image.pixelColor(horizontal, vertical).alpha()
                                > 0
                                for horizontal in range(extent)
                                for vertical in range(extent)
                            )
                        )
                images[variant] = icon.pixmap(48, 48).toImage()
        self.assertNotEqual(images["windows311"], images["workbench"])
        self.assertNotEqual(images["modern"], images["workbench"])

    @staticmethod
    def contrast_ratio(foreground, background):
        def luminance(value):
            channels = []
            for index in (1, 3, 5):
                channel = int(value[index : index + 2], 16) / 255
                channels.append(
                    channel / 12.92
                    if channel <= 0.03928
                    else ((channel + 0.055) / 1.055) ** 2.4
                )
            return (
                0.2126 * channels[0]
                + 0.7152 * channels[1]
                + 0.0722 * channels[2]
            )

        lighter, darker = sorted(
            (luminance(foreground), luminance(background)), reverse=True
        )
        return (lighter + 0.05) / (darker + 0.05)

    def test_modern_skins_resolve_all_tokens_and_differ(self):
        from fsui.qt import QColor, modern_theme

        self.assertEqual(modern_theme.DEFAULT_SKIN, "modern")
        self.assertEqual(
            list(modern_theme.SKINS),
            ["modern", "cyberpunk", "synthwave", "hologram", "terminal"],
        )
        windows = set()
        for name, skin in modern_theme.SKINS.items():
            with self.subTest(skin=name):
                self.assertEqual(skin.name, name)
                rendered = modern_theme.render(modern_theme.STYLESHEET, name)
                self.assertNotIn("@", rendered)
                self.assertIn(skin.accent, rendered)
                self.assertIn(f"border-radius: {skin.radius}px", rendered)
                # Every skin is dark with readable text.
                self.assertLess(QColor(skin.window).lightness(), 60)
                self.assertGreater(QColor(skin.text).lightness(), 170)
                self.assertGreater(
                    QColor(skin.accent).lightness(),
                    QColor(skin.pressed).lightness(),
                )
                windows.add(skin.window)
                self.assertGreaterEqual(
                    self.contrast_ratio(skin.accent_soft, skin.pressed), 4.5
                )
                self.assertGreaterEqual(
                    self.contrast_ratio(skin.accent_text, skin.accent), 4.5
                )
                self.assertGreaterEqual(
                    self.contrast_ratio(skin.nav_text, skin.nav), 4.5
                )
        self.assertEqual(len(windows), len(modern_theme.SKINS))
        self.assertEqual(
            modern_theme.render("@icons@/check.svg", "modern").endswith(
                "/res/check.svg"
            ),
            True,
        )
        self.assertEqual(
            modern_theme.palette("not-a-skin"), modern_theme.MODERN
        )

    def test_modern_skin_selection(self):
        from fsui.qt import QPalette, modern_theme
        from fsui.qt.qt import initialize_qt_style

        palette = self.application.palette()
        stylesheet = self.application.styleSheet()
        font = self.application.font()
        state = fsui.theme, fsui.theme_variant, fsui.theme_skin
        try:
            for name, skin in modern_theme.SKINS.items():
                for command_line in (False, True):
                    with self.subTest(skin=name, command_line=command_line):
                        arguments = ["fs-uae-launcher"]
                        if command_line:
                            arguments.append("--launcher-theme=fusion-" + name)
                        with patch("fsui.qt.qt.Settings.instance") as settings:
                            settings.return_value.get.side_effect = (
                                lambda key: (
                                    (
                                        "fusion-modern"
                                        if command_line
                                        else "fusion-" + name
                                    )
                                    if key == "launcher_theme"
                                    else ""
                                )
                            )
                            with patch("sys.argv", arguments):
                                initialize_qt_style(self.application)
                            settings.return_value.set.assert_not_called()
                        self.assertEqual(fsui.theme_variant, "modern")
                        self.assertEqual(fsui.theme_skin, name)
                        self.assertIs(modern_theme.palette(), skin)
                        self.assertEqual(
                            self.application.palette()
                            .color(QPalette.ColorRole.Window)
                            .name(),
                            skin.window,
                        )
                        self.assertEqual(
                            self.application.palette()
                            .color(QPalette.ColorRole.Link)
                            .name(),
                            skin.accent,
                        )
                        self.assertNotIn("@", self.application.styleSheet())
                        self.assertIn(
                            skin.accent, self.application.styleSheet()
                        )
            # Plain and retro themes leave the active skin at Modern Dark.
            with patch("fsui.qt.qt.Settings.instance") as settings:
                settings.return_value.get.side_effect = lambda key: (
                    "fusion-plain" if key == "launcher_theme" else ""
                )
                with patch("sys.argv", ["fs-uae-launcher"]):
                    initialize_qt_style(self.application)
            self.assertEqual(fsui.theme_skin, "")
        finally:
            modern_theme.apply_modern_theme(self.application, "modern")
            self.application.setPalette(palette)
            self.application.setStyleSheet(stylesheet)
            self.application.setFont(font)
            fsui.theme, fsui.theme_variant, fsui.theme_skin = state

    def test_modern_skin_colours_reach_navigation_and_icons(self):
        import qtawesome as qta
        from fsui.qt import modern_theme
        from launcher.ui.navigation_icons import navigation_icon
        from launcher.ui.pageddialog import PagedDialog

        palette = self.application.palette()
        stylesheet = self.application.styleSheet()
        font = self.application.font()
        state = fsui.theme, fsui.theme_variant, fsui.theme_skin
        try:
            for name in ("cyberpunk", "hologram", "terminal"):
                with self.subTest(skin=name):
                    modern_theme.apply_modern_theme(self.application, name)
                    skin = modern_theme.palette()
                    with patch.object(
                        fsui, "theme_variant", "modern"
                    ), patch.object(fsui, "theme_skin", name):
                        with patch(
                            "launcher.ui.navigation_icons.qta.icon",
                            wraps=qta.icon,
                        ) as icon:
                            navigation_icon("fa5s.save")
                            icon.assert_called_with(
                                "fa5s.save", color=skin.icon
                            )
                            navigation_icon("fa5s.play", on_accent=True)
                            icon.assert_called_with(
                                "fa5s.play", color=skin.accent_text
                            )
                        self.setup_dialog()
                        paged = PagedDialog(self.dialog, "Skins")
                        self.assertIn(skin.nav, paged.list_view.styleSheet())
                        self.assertIn(
                            skin.accent_soft, paged.list_view.styleSheet()
                        )
                        self.assertNotIn(
                            "#1c1e2b", paged.list_view.styleSheet()
                        )
                        paged.close()
                        self.run_dialog()
        finally:
            modern_theme.apply_modern_theme(self.application, "modern")
            self.application.setPalette(palette)
            self.application.setStyleSheet(stylesheet)
            self.application.setFont(font)
            fsui.theme, fsui.theme_variant, fsui.theme_skin = state

    def test_modern_skin_colours_reach_media_strip(self):
        from types import SimpleNamespace
        from fsui.qt import QWidget, modern_theme
        from launcher.ui.bottombar.BottomPanel import BottomPanel
        from launcher.ui.bottombar.GameInfoPanel import GameInfoPanel
        from launcher.ui.bottombar.ScreenshotsPanel import ScreenshotsPanel

        palette = self.application.palette()
        stylesheet = self.application.styleSheet()
        font = self.application.font()
        widget = QWidget()
        try:
            for name in modern_theme.SKINS:
                with self.subTest(skin=name):
                    modern_theme.apply_modern_theme(self.application, name)
                    skin = modern_theme.palette()
                    dc = Mock()
                    # Just what the modern painters read, without the
                    # settings listeners and image loaders the panels start.
                    panel = SimpleNamespace(
                        size=lambda: (400, 160),
                        widget=lambda: widget,
                        create_dc=lambda: dc,
                        images=[],
                        default_image=None,
                        image=None,
                        x_offset=0,
                        title="Title",
                        year="1990",
                        companies="Company",
                        sub_title="Variant",
                    )
                    panel.draw_background = (
                        lambda dc: BottomPanel.draw_background(panel, dc)
                    )
                    with patch.object(fsui, "theme_variant", "modern"):
                        ScreenshotsPanel.on_paint(panel)
                        GameInfoPanel.draw_modern_info(panel, dc)
                    self.assertEqual(
                        dc.draw_rectangle.call_args.args[4].name(),
                        skin.surface,
                    )
                    self.assertEqual(
                        [
                            c.args[0].name()
                            for c in dc.set_text_color.call_args_list
                        ],
                        [
                            skin.text,
                            skin.muted,
                            skin.muted,
                            skin.text,
                            skin.muted,
                        ],
                    )
        finally:
            modern_theme.apply_modern_theme(self.application, "modern")
            self.application.setPalette(palette)
            self.application.setStyleSheet(stylesheet)
            self.application.setFont(font)

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
                    with self.subTest(
                        variant=variant, command_line=command_line
                    ):
                        arguments = ["fs-uae-launcher"]
                        if command_line:
                            arguments.append(
                                "--launcher-theme=fusion-" + variant
                            )
                        with patch("fsui.qt.qt.Settings.instance") as settings:
                            settings.return_value.get.side_effect = (
                                lambda key: (
                                    (
                                        "fusion-modern"
                                        if command_line
                                        else "fusion-" + variant
                                    )
                                    if key == "launcher_theme"
                                    else ""
                                )
                            )
                            with patch("sys.argv", arguments):
                                initialize_qt_style(self.application)
                        self.assertEqual(fsui.theme_variant, variant)
                        self.assertEqual(
                            self.application.palette()
                            .color(QPalette.ColorRole.Window)
                            .name(),
                            background,
                        )
                        self.assertEqual(
                            self.application.palette()
                            .color(QPalette.ColorRole.Highlight)
                            .name(),
                            highlight,
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
                "fusion-plain",
                "standard",
                "native",
                "fusion",
                "fusion-adwaita",
                "fusion-dark",
                "fusion-windows10",
                "fws",
                "unknown-theme",
            ):
                for command_line in (False, True):
                    with self.subTest(saved=saved, command_line=command_line):
                        arguments = ["fs-uae-launcher"]
                        if command_line:
                            arguments.append("--launcher-theme=" + saved)
                        with patch("fsui.qt.qt.Settings.instance") as settings:
                            settings.return_value.get.side_effect = (
                                lambda key: (
                                    (
                                        "fusion-modern"
                                        if command_line
                                        else saved
                                    )
                                    if key == "launcher_theme"
                                    else ""
                                )
                            )
                            with patch("sys.argv", arguments):
                                initialize_qt_style(self.application)
                            if saved != "fusion-plain":
                                settings.return_value.set.assert_called_with(
                                    "launcher_theme", "fusion-plain"
                                )
                        self.assertEqual(fsui.theme_variant, "plain")
                        self.assertEqual(self.application.styleSheet(), "")
                        self.assertGreater(
                            self.application.palette()
                            .color(QPalette.ColorRole.Window)
                            .lightness(),
                            150,
                        )
                        self.assertLess(
                            self.application.palette()
                            .color(QPalette.ColorRole.Text)
                            .lightness(),
                            100,
                        )
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
                help_button = HelpButton(
                    self.dialog, "https://fs-uae.net/options"
                )
                info_button = IconButton(self.dialog, "info.png")
                self.assertEqual(icons.call_count, 2)
                icons.assert_called_with("fa5s.info-circle", color="#9bcce2")
                for button in (help_button, info_button):
                    self.assertFalse(button.widget().icon().isNull())
                    self.assertEqual(button.widget().iconSize().width(), 18)
                with patch(
                    "launcher.ui.HelpButton.open_url_in_browser"
                ) as open_url:
                    help_button.widget().click()
                    open_url.assert_called_once_with(
                        "https://fs-uae.net/options"
                    )
        with patch.object(fsui, "theme_variant", "windows311"):
            with patch("qtawesome.icon") as icons:
                IconButton(self.dialog, "info.png")
                icons.assert_not_called()
        self.run_dialog()

    def test_image_button(self):
        self.setup_dialog()
        image = QImage(16, 16, QImage.Format.Format_ARGB32)
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
        QTimer.singleShot(
            0, lambda: dialog.end_modal(QDialog.DialogCode.Accepted)
        )
        self.assertEqual(dialog.show_modal(), QDialog.DialogCode.Accepted)

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
        image = QImage(200, 100, QImage.Format.Format_ARGB32)
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

    def test_behaviors_stop_listening_when_their_widget_is_deleted(self):
        import shiboken6
        from fsui.qt import QWidget
        from launcher.launcher_config import LauncherConfig
        from launcher.launcher_settings import LauncherSettings
        from launcher.ui.behaviors.configbehavior import ConfigBehavior
        from launcher.ui.behaviors.settingsbehavior import SettingsBehavior

        class Watcher(QWidget):
            def on_zoom_config(self, value):
                pass

            def on_zoom_setting(self, value):
                pass

        for behavior_class, store in (
            (ConfigBehavior, LauncherConfig),
            (SettingsBehavior, LauncherSettings),
        ):
            with self.subTest(behavior=behavior_class.__name__):
                widget = Watcher()
                behavior = behavior_class(widget, ["zoom"])
                with patch.object(store, "remove_listener") as remove_listener:
                    # The C++ object is gone by the time destroyed fires.
                    shiboken6.delete(widget)
                remove_listener.assert_called_once_with(behavior)


class TestLaunchAndNetplay(WidgetTestCase):
    def test_configuration_row_delete_confirmation_and_refresh(self):
        import tempfile
        from pathlib import Path
        from qtpy.QtTest import QTest
        from fsui.qt import QMessageBox, Qt
        from launcher.ui.ConfigurationsBrowser import (
            ConfigurationItemDelegate,
            ConfigurationsBrowser,
        )

        self.setup_dialog()
        self.dialog.layout = fsui.VerticalLayout()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Test.fs-uae"
            path.write_text("[fs-uae]\n")
            item = {
                "uuid": None,
                "name": "Test",
                "path": str(path),
                "have": 5,
                "platform": "",
                "published": 1,
                "sort_key": "test",
            }
            settings = {"config_path": str(path)}
            with patch(
                "launcher.ui.ConfigurationsBrowser.Database.get_instance"
            ) as database_factory, patch(
                "launcher.ui.ConfigurationsBrowser.LauncherSettings.get",
                side_effect=lambda key: settings.get(key, ""),
            ), patch(
                "launcher.ui.ConfigurationsBrowser.LauncherSettings.set"
            ) as set_setting, patch(
                "launcher.ui.ConfigurationsBrowser.LauncherConfig.load_file"
            ) as load, patch(
                "launcher.ui.ConfigurationsBrowser.LauncherConfig.load_default_config"
            ) as reset, patch(
                "launcher.ui.ConfigurationsBrowser.ConfigurationScanner.delete_configuration"
            ) as delete, patch(
                "launcher.scanner.Scanner.running", False
            ):
                database = database_factory.return_value
                database.find_games_new.return_value = [item]
                database.decode_path.side_effect = lambda value: value
                browser = ConfigurationsBrowser(self.dialog)
                self.dialog.layout.add(browser, fill=True, expand=True)

                def setting_changed(key, value):
                    settings[key] = value
                    browser.on_setting(key, value)

                set_setting.side_effect = setting_changed

                def delete_file(database, filename):
                    Path(filename).unlink()
                    database.find_games_new.return_value = []

                delete.side_effect = delete_file
                self.dialog.set_size((540, 300))
                self.dialog.show()
                self.application.processEvents()
                index = browser.model.index(0, 0)
                rect = ConfigurationItemDelegate.delete_rect(
                    browser.visualRect(index)
                )
                with patch(
                    "fsui.qt.QMessageBox.question",
                    return_value=QMessageBox.StandardButton.No,
                ):
                    QTest.mouseClick(
                        browser.viewport(),
                        Qt.MouseButton.LeftButton,
                        pos=rect.center(),
                    )
                    with patch(
                        "launcher.launcherapp.LauncherApp.start_game"
                    ) as start:
                        QTest.mouseDClick(
                            browser.viewport(),
                            Qt.MouseButton.LeftButton,
                            pos=rect.center(),
                        )
                        start.assert_not_called()
                delete.assert_not_called()
                load.assert_not_called()
                self.assertTrue(path.exists())
                with patch(
                    "fsui.qt.QMessageBox.question",
                    return_value=QMessageBox.StandardButton.Yes,
                ) as confirmation:
                    QTest.mouseClick(
                        browser.viewport(),
                        Qt.MouseButton.LeftButton,
                        pos=rect.center(),
                    )
                self.assertIn(str(path), confirmation.call_args.args[2])
                delete.assert_called_once_with(database, str(path))
                reset.assert_called_once_with()
                self.assertFalse(path.exists())
                self.assertEqual(browser.model.rowCount(index), 0)
                self.assertIsNone(browser.get_index())
        self.run_dialog()

    def test_configuration_delete_preserves_other_selected_configuration(self):
        from fsui.qt import QMessageBox
        from launcher.ui.ConfigurationsBrowser import ConfigurationsBrowser

        self.setup_dialog()
        kept = {
            "uuid": None,
            "name": "Keep",
            "path": "/tmp/Keep.fs-uae",
            "have": 5,
            "platform": "",
            "published": 1,
            "sort_key": "keep",
        }
        removed = dict(kept, name="Remove", path="/tmp/Remove.fs-uae")
        settings = {"config_path": kept["path"]}
        with patch(
            "launcher.ui.ConfigurationsBrowser.Database.get_instance"
        ) as database_factory, patch(
            "launcher.ui.ConfigurationsBrowser.LauncherSettings.get",
            side_effect=lambda key: settings.get(key, ""),
        ), patch(
            "launcher.ui.ConfigurationsBrowser.LauncherSettings.set"
        ) as set_setting, patch(
            "launcher.ui.ConfigurationsBrowser.LauncherConfig.load_file"
        ) as load, patch(
            "launcher.ui.ConfigurationsBrowser.LauncherConfig.load_default_config"
        ) as reset, patch(
            "launcher.ui.ConfigurationsBrowser.ConfigurationScanner.delete_configuration"
        ) as delete, patch(
            "fsui.qt.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ), patch(
            "launcher.scanner.Scanner.running", False
        ):
            database = database_factory.return_value
            database.find_games_new.return_value = [kept, removed]
            database.decode_path.side_effect = lambda value: value
            browser = ConfigurationsBrowser(self.dialog)
            browser.select_item(0)
            load.reset_mock()
            set_setting.side_effect = browser.on_setting
            delete.side_effect = lambda *arguments: setattr(
                database.find_games_new, "return_value", [kept]
            )
            browser.delete_configuration(1)
            self.assertEqual(browser.get_index(), 0)
            self.assertEqual(browser.items[0]["path"], kept["path"])
            reset.assert_not_called()
            load.assert_not_called()
        self.run_dialog()

    def test_configuration_delete_protects_database_entries_and_reports_errors(
        self,
    ):
        from qtpy.QtTest import QTest
        from fsui.qt import QMessageBox, Qt
        from launcher.ui.ConfigurationsBrowser import ConfigurationsBrowser

        self.setup_dialog()
        item = {
            "uuid": "database-game",
            "name": "Game",
            "path": "/tmp/Test.fs-uae",
            "have": 5,
            "platform": "",
            "published": 1,
            "sort_key": "game",
        }
        with patch(
            "launcher.ui.ConfigurationsBrowser.Database.get_instance"
        ) as database_factory, patch(
            "launcher.ui.ConfigurationsBrowser.LauncherSettings.get",
            return_value="",
        ), patch(
            "launcher.ui.ConfigurationsBrowser.ConfigurationScanner.delete_configuration"
        ) as delete, patch(
            "fsui.qt.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ) as confirmation, patch(
            "fsui.show_error"
        ) as error, patch(
            "launcher.scanner.Scanner.running", False
        ):
            database = database_factory.return_value
            database.find_games_new.return_value = [item]
            database.decode_path.side_effect = lambda value: value
            browser = ConfigurationsBrowser(self.dialog)
            self.assertFalse(browser.can_delete_configuration(0))
            browser.delete_configuration(0)
            confirmation.assert_not_called()
            item["uuid"] = None
            delete.side_effect = PermissionError("Permission denied")
            browser.delete_configuration(0)
            error.assert_called_once()
            self.assertEqual(browser.get_item_count(), 1)
            browser.selectionModel().blockSignals(True)
            browser.select_item(0)
            browser.selectionModel().blockSignals(False)
            QTest.keyClick(browser, Qt.Key.Key_Delete)
            self.assertEqual(delete.call_count, 2)
            with patch("launcher.scanner.Scanner.running", True):
                browser.delete_configuration(0)
            self.assertEqual(delete.call_count, 2)
        self.run_dialog()

    def test_restart_command_and_shutdown_order(self):
        from types import SimpleNamespace
        from launcher.launcherapp import LauncherApp

        for frozen in (False, True):
            with self.subTest(frozen=frozen):
                application = SimpleNamespace(
                    _restart_arguments=None,
                    qapplication=Mock(),
                    save_settings=Mock(),
                )
                calls = []
                application.save_settings.side_effect = lambda: calls.append(
                    "save"
                )
                application.qapplication.closeAllWindows.side_effect = (
                    lambda: calls.append("close")
                )
                application.qapplication.quit.side_effect = (
                    lambda: calls.append("quit")
                )
                with patch(
                    "sys.argv",
                    [
                        "fs-uae-launcher",
                        "--launcher-theme=fusion-modern",
                        "game.adf",
                    ],
                ):
                    with patch("sys.executable", "/test/python"), patch(
                        "sys.frozen", frozen, create=True
                    ):
                        with patch(
                            "fsboot.base_dir", return_value="/test/Amiga Data"
                        ):
                            LauncherApp.request_restart(application)
                            LauncherApp.request_restart(application)
                self.assertEqual(calls, ["save", "close", "quit"])
                self.assertEqual(
                    application._restart_arguments[0], "/test/python"
                )
                self.assertEqual(
                    application._restart_arguments[-1],
                    "--base-dir=/test/Amiga Data",
                )
                self.assertEqual(
                    len(application._restart_arguments), 2 if frozen else 3
                )
                self.assertNotIn("game.adf", application._restart_arguments)
                self.assertNotIn(
                    "--launcher-theme=fusion-modern",
                    application._restart_arguments,
                )
                with patch("launcher.launcherapp.os.execv") as execute:
                    LauncherApp.restart_if_requested(application)
                    execute.assert_called_once_with(
                        application._restart_arguments[0],
                        application._restart_arguments,
                    )

    def test_restart_save_failure_keeps_windows_open(self):
        from types import SimpleNamespace
        from launcher.launcherapp import LauncherApp

        application = SimpleNamespace(
            _restart_arguments=None,
            qapplication=Mock(),
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
                with patch(
                    "launcher.launcherapp.LauncherApp"
                ) as application_class:
                    application = application_class.return_value
                    application.run.side_effect = lambda: events.append("run")
                    application.save_settings.side_effect = (
                        lambda: events.append("save")
                    )

                    def restart():
                        events.append("restart")
                        if restart_failure:
                            raise OSError("Executable unavailable")

                    application.restart_if_requested.side_effect = restart
                    with patch("fsbc.signal.Signal") as signal, patch(
                        "sys.argv", ["fs-uae-launcher"]
                    ):
                        signal.return_value.notify.side_effect = (
                            lambda: events.append("notify")
                        )
                        with patch("fsui.show_error") as show_error:
                            app_main()
                            self.assertEqual(
                                events, ["run", "save", "notify", "restart"]
                            )
                            self.assertEqual(
                                show_error.call_count, int(restart_failure)
                            )

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
                source,
                root / "portable data",
                root / "Portable.ini",
                True,
                root / "preferences" / "base-dir",
            )
            application = SimpleNamespace(
                _restart_arguments=None,
                qapplication=Mock(),
                save_settings=Mock(
                    side_effect=lambda: settings.write_text(
                        "[settings]\nstate = saved\n"
                    )
                ),
            )
            with patch("sys.argv", ["fs-uae-launcher"]), patch(
                "fsboot.base_dir", return_value=str(source)
            ), patch("launcher.scanner.Scanner.running", False):
                LauncherApp.request_restart(
                    application, portable_change=change
                )
            self.assertFalse(change.marker.exists())
            settings.write_text("[settings]\nstate = final shutdown save\n")
            with patch("launcher.launcherapp.os.execv") as execute:
                LauncherApp.restart_if_requested(application)
                execute.assert_called_once()
            self.assertIn(
                "final shutdown save",
                (change.destination / "Data" / "Settings.ini").read_text(),
            )
            self.assertEqual(
                application._restart_arguments[-1],
                "--base-dir=" + str(change.destination),
            )

    def test_portable_restart_failure_does_not_relaunch(self):
        from types import SimpleNamespace
        from launcher.launcherapp import LauncherApp

        change = Mock()
        change.apply.side_effect = OSError("Disk full")
        application = SimpleNamespace(
            _restart_arguments=["python", "--base-dir=/original"],
            _portable_change=change,
            qapplication=Mock(),
        )
        with patch("launcher.launcherapp.os.execv") as execute:
            with self.assertRaisesRegex(OSError, "original data"):
                LauncherApp.restart_if_requested(application)
            execute.assert_not_called()
        self.assertEqual(
            application._restart_arguments[-1], "--base-dir=/original"
        )

    def test_default_chat_color_uses_current_palette(self):
        from fsui.qt import QColor, QPalette

        self.setup_dialog()
        text = fsui.TextArea(self.dialog)
        for color in ("#edf0f7", "#121212"):
            palette = text.palette()
            palette.setColor(QPalette.ColorRole.Text, QColor(color))
            text.setPalette(palette)
            text.append_text("Joined channel", color=(64, 164, 64))
            text.append_text("Default colour", color=None)
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

    def test_start_while_in_a_netplay_game(self):
        from launcher.launcherapp import LauncherApp

        netplay = Mock(session=Mock(), joining=None)
        netplay.start_requested.return_value = (
            "Waiting: Dave is missing files."
        )
        with patch(
            "launcher.netplay.netplay.Netplay.current", return_value=netplay
        ), patch.object(LauncherApp, "start_local_game") as local, patch(
            "launcher.launcherapp.fsui.show_warning"
        ) as warn:
            LauncherApp.start_game()
            local.assert_not_called()
            warn.assert_called_once_with(
                "Waiting: Dave is missing files.", "Net Play"
            )
        with patch(
            "launcher.netplay.netplay.Netplay.current", return_value=None
        ), patch.object(LauncherApp, "start_local_game") as local:
            LauncherApp.start_game()
            local.assert_called_once_with()

    def test_launch_dialog_netplay_context(self):
        from launcher.ui.launch import LaunchDialog

        for game in ("", "4d5211d9-2761"):
            with self.subTest(game=game):
                with patch("launcher.ui.launch.LauncherConfig") as config:
                    config.get.side_effect = lambda key: (
                        game if key == "__netplay_game" else ""
                    )
                    task = Mock()
                    dialog = LaunchDialog(None, "Launching test", task)
                    self.assertEqual(dialog.netplay_game_id, game)
                    task.progressed.connect.assert_called_once_with(
                        dialog.on_progress
                    )
                    task.finished.connect.assert_called_once_with(
                        dialog.on_complete
                    )
                    task.failed.connect.assert_called_once_with(
                        dialog.on_error
                    )
                    dialog.was_closed = True
                    dialog.close()

    def test_text_input_dialog_selects_default_text(self):
        from fsui.qt import QEvent
        from launcher.netplay.text_input_dialog import SimpleTextInputDialog

        self.setup_dialog()
        for title in ("Barbarian", "Shadow of the Beast", "new"):
            with self.subTest(title=title):
                dialog = SimpleTextInputDialog(
                    self.dialog,
                    "Enter Game Name",
                    "Game Name:",
                    default_text=title,
                )
                self.assertEqual(dialog.text_field.get_text(), title)
                self.assertEqual(dialog.text_field.selectedText(), title)
                dialog.reject()
                dialog.deleteLater()
                self.application.sendPostedEvents(
                    None, QEvent.Type.DeferredDelete
                )
        self.run_dialog()

    def test_lobby_servers_group(self):
        from fsbc.settings import Settings
        from launcher.settings.lobby_servers_group import LobbyServersGroup

        settings = Settings()
        settings._loaded = True
        settings._atexit_registered = True
        settings.verbose = False
        settings.values["netplay_servers"] = "b.example;a.example:25200"
        self.setup_dialog()
        with patch.object(Settings, "_instance", settings):
            group = LobbyServersGroup(self.dialog)
            try:
                self.assertEqual(group.list_view.get_item_count(), 2)
                self.assertFalse(group.remove_button.is_enabled())
                prompt = "launcher.settings.lobby_servers_group.SimpleTextInputDialog.get_text"
                with patch(prompt, return_value=" C.Example:25101 "):
                    group.on_add_button()
                self.assertEqual(
                    settings.values["netplay_servers"],
                    "b.example;a.example:25200;c.example",
                )
                self.assertEqual(group.list_view.get_item_count(), 3)
                with patch(prompt, return_value="c.example"), patch(
                    "launcher.settings.lobby_servers_group.fsui.show_error"
                ) as error:
                    group.on_add_button()
                    self.assertIn("already", error.call_args.args[0])
                with patch(prompt, return_value=None):
                    group.on_add_button()
                self.assertEqual(group.list_view.get_item_count(), 3)
                group.list_view.set_index(0)
                group.on_select_item(0)
                self.assertTrue(group.remove_button.is_enabled())
                group.on_remove_button()
                self.assertEqual(
                    settings.values["netplay_servers"],
                    "a.example:25200;c.example",
                )
                self.assertFalse(group.remove_button.is_enabled())
            finally:
                group.on_destroy()
        self.run_dialog()

    def test_lobby_browser_panel(self):
        from launcher.netplay.lobby_browser import (
            LOCAL,
            NO_LISTING,
            ONLINE,
            UNREACHABLE,
            LobbyBrowser,
        )
        from launcher.netplay.lobby_browser_panel import LobbyBrowserPanel

        class Watcher:
            def __init__(self, client, member, name, on_listing, on_state):
                self.on_listing, self.on_state = on_listing, on_state
                self.retried = 0

            def start(self):
                pass

            def stop(self):
                pass

            def retry(self):
                self.retried += 1

        netplay = Mock(
            browser_listeners=[],
            activity_listeners=[],
            session_listeners=[],
            session=None,
            joining=None,
            session_title=None,
            session_server=None,
            session_hosted=False,
            session_listed=True,
        )
        netplay.running_local_lobby.return_value = None
        netplay.local_lobby_address.return_value = None
        netplay.activity_log = [(0, "Earlier line", False)]
        netplay.browser = LobbyBrowser(
            name=lambda: "Paul",
            dispatch=lambda f, *a: f(*a),
            on_change=lambda: [f() for f in netplay.browser_listeners],
            on_message=lambda text, warning=False: [
                f((0, text, warning)) for f in netplay.activity_listeners
            ],
            client_factory=lambda host, port: None,
            watcher_factory=Watcher,
        )
        opened = []
        self.setup_dialog()
        panel = LobbyBrowserPanel(
            netplay, open_settings=lambda: opened.append(1)
        )
        try:
            # Nothing to browse yet.
            self.assertFalse(panel.no_servers.isHidden())
            self.assertTrue(panel.servers_tree.isHidden())
            panel.add_server_button.click()
            self.assertEqual(opened, [1])
            self.assertIn("Earlier line", panel.activity.toPlainText())

            browser = netplay.browser
            browser.set_servers(
                ["netplay.example.net", "old.example.org", "gone.example"]
            )
            browser.set_local(25101)
            local = browser.server(LOCAL).watcher
            local.on_state(ONLINE, None, None)
            local.on_listing(
                {
                    "id": "mine",
                    "revision": 1,
                    "presence": True,
                    "online": ["Dave", "Paul"],
                    "games": [],
                }
            )
            club = browser.server("netplay.example.net").watcher
            club.on_state(ONLINE, None, None)
            club.on_listing(
                {
                    "id": "club",
                    "name": "Amiga Friday",
                    "revision": 3,
                    "games": [
                        {
                            "id": "g1",
                            "title": "Sensible Soccer",
                            "host": "Kim",
                            "state": "configuring",
                            "players": 2,
                            "joined": 1,
                        },
                        {
                            "id": "g2",
                            "title": "Speedball 2",
                            "host": "Lee",
                            "state": "created",
                            "players": 2,
                            "joined": 2,
                        },
                        {
                            "id": "g3",
                            "title": "Turrican II",
                            "host": "Ash",
                            "state": "running",
                            "players": 2,
                            "joined": 2,
                        },
                        {
                            "id": "g4",
                            "title": "<b>Bold</b>",
                            "host": "Eve",
                            "state": "created",
                            "players": 2,
                            "joined": 1,
                        },
                    ],
                }
            )
            old = browser.server("old.example.org").watcher
            old.on_state(UNREACHABLE, "connection refused", 40)
            browser.server("gone.example").watcher.on_state(
                NO_LISTING, "doesn't list games (older server?)", None
            )

            tree = panel.servers_tree
            rows = [
                tree.topLevelItem(i) for i in range(tree.topLevelItemCount())
            ]
            self.assertEqual(
                [(row.text(0).strip(), row.text(1)) for row in rows],
                [
                    ("● This computer", "no games"),
                    ("Online: Dave, Paul (you)", ""),
                    ("● Amiga Friday (netplay.example.net)", "4 games"),
                    ("○ old.example.org", "can't reach it, retrying in 40 s"),
                    ("○ gone.example", "doesn't list games (older server?)"),
                ],
            )
            retry = tree.itemWidget(rows[3], 2)
            retry.click()
            self.assertEqual(old.retried, 1)
            self.assertTrue(panel.countdown.isActive())

            games = panel.games_tree
            rows = [
                games.topLevelItem(i) for i in range(games.topLevelItemCount())
            ]
            self.assertEqual(
                [[row.text(c) for c in range(5)] for row in rows],
                [
                    ["<b>Bold</b>", "Eve", "1 of 2", "Amiga Friday", ""],
                    ["Sensible Soccer", "Kim", "1 of 2", "Amiga Friday", ""],
                    ["Speedball 2", "Lee", "2 of 2", "Amiga Friday", "full"],
                    ["Turrican II", "Ash", "running", "Amiga Friday", ""],
                ],
            )
            self.assertEqual(
                [row.isDisabled() for row in rows], [False, False, True, True]
            )
            self.assertEqual(
                [games.itemWidget(row, 4) is not None for row in rows],
                [True, True, False, False],
            )
            games.itemWidget(rows[1], 4).click()
            netplay.join_game.assert_called_once_with(
                "netplay.example.net",
                25101,
                "g1",
                title="Sensible Soccer",
                server="Amiga Friday",
            )
            netplay.join_game.reset_mock()
            dialog = "launcher.netplay.lobby_browser_panel.JoinByIdDialog.get"
            with patch(dialog, return_value=("This computer", "g9")) as ask:
                panel.join_by_id_button.click()
            self.assertEqual(ask.call_args.args[1][0], "This computer")
            self.assertIn("netplay.example.net", ask.call_args.args[1])
            netplay.join_game.assert_called_once_with(
                "127.0.0.1", 25101, "g9", server="This computer"
            )
            netplay.join_game.reset_mock()
            with patch(dialog, return_value=("[2001:db8::1]:25200", "g8")):
                panel.join_by_id_button.click()
            netplay.join_game.assert_called_once_with(
                "2001:db8::1", 25200, "g8", server="[2001:db8::1]:25200"
            )
            netplay.join_game.reset_mock()
            with patch(dialog, return_value=None):
                panel.join_by_id_button.click()
            netplay.join_game.assert_not_called()
            self.assertTrue(panel.no_games.isHidden())
            self.assertIn(
                "Connected to Amiga Friday", panel.activity.toPlainText()
            )

            old.on_state(ONLINE, None, None)
            old.on_listing({"id": "old", "revision": 1, "games": []})
            browser.server("gone.example").watcher.on_state(ONLINE, None, None)
            self.assertFalse(panel.countdown.isActive())

            # In a game: the game replaces browsing until it ends.
            self.assertIs(panel.pages.currentWidget(), panel.browse_page)
            netplay.joining = "g1"
            panel.on_session(None)
            self.assertIs(panel.pages.currentWidget(), panel.game_page)
            self.assertEqual(panel.game_heading.text(), "Joining\u2026")
            session = Mock(
                game_id="g1",
                is_host=False,
                started=False,
                snapshot={"slots": [{"slot": 0, "tag": "Paul"}]},
            )
            session.slot_lines.return_value = [
                "1. Paul \u2014 ready",
                "2. Dave (you) \u2014 missing: floppy_drive_0",
            ]
            session.status_line.return_value = "Starts when you're ready: add the missing file, then Re-check."
            netplay.joining, netplay.session = None, session
            netplay.session_title, netplay.session_server = (
                "Sensible Soccer",
                "Dave's lobby",
            )
            panel.on_session(session)
            self.assertEqual(
                panel.game_heading.text(),
                "Sensible Soccer, hosted by Paul on Dave's lobby",
            )
            self.assertEqual(panel.slot_list.count(), 2)
            self.assertIn("Re-check", panel.game_status.text())
            self.assertEqual(panel.leave_button.text(), "Leave")
            panel.recheck_button.click()
            netplay.recheck.assert_called_once_with()
            panel.leave_button.click()
            netplay.leave_game.assert_called_once_with()
            session.is_host = True
            panel.on_session(session)
            self.assertEqual(panel.leave_button.text(), "End game")
            self.assertIn("hosted by you", panel.game_heading.text())
            netplay.session = None
            panel.on_session(None)
            self.assertIs(panel.pages.currentWidget(), panel.browse_page)
        finally:
            panel.shutdown()
            self.assertEqual(netplay.browser_listeners, [])
            self.assertEqual(netplay.activity_listeners, [])
            self.assertEqual(netplay.session_listeners, [])
            panel.deleteLater()
        self.run_dialog()

    def test_lobby_browser_panel_hosting(self):
        from fsbc.settings import Settings
        from fsui.qt import QApplication
        from launcher.netplay.lobby_browser import LOCAL, ONLINE, LobbyBrowser
        from launcher.netplay.lobby_browser_panel import (
            HostGameDialog,
            LobbyBrowserPanel,
        )
        from launcher.netplay.netplay import HOSTING

        class Watcher:
            def __init__(self, client, member, name, on_listing, on_state):
                self.on_listing, self.on_state = on_listing, on_state

            def start(self):
                pass

            def stop(self):
                pass

        settings = Settings()
        settings._loaded = True
        settings._atexit_registered = True
        settings.verbose = False
        settings.values.update(
            {
                "config_name": "Unnamed Configuration",
                "netplay_public_address": "198.51.100.7",
                "netplay_last_host_server": "club.example",
            }
        )
        netplay = Mock(
            browser_listeners=[],
            activity_listeners=[],
            session_listeners=[],
            activity_log=[],
            session=None,
            joining=None,
            session_title=None,
            session_server=None,
            session_hosted=False,
            session_listed=True,
        )
        netplay.running_local_lobby.return_value = None
        netplay.local_lobby_address.return_value = None
        netplay.browser = LobbyBrowser(
            name=lambda: "Paul",
            dispatch=lambda f, *a: f(*a),
            on_change=lambda: [f() for f in netplay.browser_listeners],
            client_factory=lambda host, port: None,
            watcher_factory=Watcher,
        )
        self.setup_dialog()
        with patch.object(Settings, "_instance", settings):
            panel = LobbyBrowserPanel(netplay)
            try:
                # Nothing loaded: nothing to host.
                self.assertFalse(panel.host_button.isEnabled())
                self.assertEqual(
                    panel.host_button.toolTip(), "Choose a game first"
                )
                settings.set("config_path", "/configs/Sensible Soccer.fs-uae")
                settings.set("config_name", "Sensible Soccer")
                self.assertTrue(panel.host_button.isEnabled())
                self.assertEqual(
                    panel.host_button.text(), "Host game: Sensible Soccer…"
                )

                browser = netplay.browser
                browser.set_servers(["club.example", "down.example"])
                club = browser.server("club.example").watcher
                club.on_state(ONLINE, None, None)
                club.on_listing(
                    {"id": "c", "name": "Club", "revision": 1, "games": []}
                )
                ask = "launcher.netplay.lobby_browser_panel.HostGameDialog.get"
                with patch(
                    ask, return_value=("club.example", 3, False)
                ) as get:
                    panel.host_button.click()
                title, choices, last = get.call_args.args[1:]
                self.assertEqual(title, "Sensible Soccer")
                self.assertEqual(
                    choices,
                    [
                        (LOCAL, "This computer (198.51.100.7)"),
                        ("club.example", "Club (club.example)"),
                    ],
                )
                self.assertEqual(last, "club.example")
                netplay.host_game.assert_called_once_with(
                    "club.example", 3, False
                )

                # The dialog itself: the last server, 2 players, listed.
                dialog = HostGameDialog(
                    panel, "Sensible Soccer", choices, "club.example"
                )
                self.assertEqual(dialog.answer(), ("club.example", 2, True))
                self.assertEqual(dialog.windowTitle(), "Host Sensible Soccer")
                dialog.players.setCurrentIndex(2)
                dialog.listed.setChecked(False)
                self.assertEqual(dialog.answer(), ("club.example", 4, False))
                dialog.deleteLater()
                dialog = HostGameDialog(panel, "X", choices, "gone.example")
                self.assertEqual(dialog.answer()[0], LOCAL)
                dialog.deleteLater()

                netplay.joining = HOSTING
                panel.on_session()
                self.assertEqual(
                    panel.game_heading.text(), "Creating the game…"
                )

                # Hosting on this computer, unlisted.
                netplay.joining = None
                netplay.session_hosted, netplay.session_listed = True, False
                netplay.session_title, netplay.session_server = (
                    "Sensible Soccer",
                    "This computer",
                )
                netplay.running_local_lobby.return_value = Mock(port=25101)
                netplay.local_lobby_address.return_value = "198.51.100.7:25101"
                browser.set_local(25101)
                local = browser.server(LOCAL).watcher
                local.on_state(ONLINE, None, None)
                local.on_listing(
                    {
                        "id": "mine",
                        "revision": 1,
                        "presence": True,
                        "online": ["Dave", "Paul", "Sam"],
                        "games": [],
                    }
                )
                session = Mock(
                    game_id="6f1c0000-aaaa",
                    is_host=True,
                    started=False,
                    snapshot={},
                )
                session.slot_lines.return_value = [
                    "1. Paul (you) — ready",
                    "2. open",
                ]
                session.status_line.return_value = (
                    "Starts when 1 more player joins and is ready."
                )
                netplay.session = session
                panel.on_session(session)
                self.assertEqual(
                    panel.game_heading.text(),
                    "Sensible Soccer, hosted by you on This computer",
                )
                self.assertEqual(
                    panel.game_online.text(), "Online in your lobby: Dave, Sam"
                )
                self.assertEqual(
                    panel.game_address.text(),
                    "Players reach you at 198.51.100.7:25101",
                )
                self.assertFalse(panel.copy_game_id_button.isHidden())
                self.assertFalse(panel.game_stop_lobby_button.isHidden())
                self.assertEqual(panel.leave_button.text(), "End game")
                panel.game_copy_address_button.click()
                self.assertEqual(
                    QApplication.clipboard().text(), "198.51.100.7:25101"
                )
                panel.copy_game_id_button.click()
                self.assertEqual(
                    QApplication.clipboard().text(), "6f1c0000-aaaa"
                )
                panel.game_stop_lobby_button.click()
                netplay.stop_lobby.assert_called_once_with()

                # Back to browsing, the lobby still running between games.
                netplay.session = None
                panel.on_session(None)
                panel.refresh()
                self.assertFalse(panel.lobby_row.isHidden())
                self.assertEqual(
                    panel.lobby_label.text(),
                    "Your lobby is running. Players reach you at 198.51.100.7:25101",
                )
                panel.stop_lobby_button.click()
                self.assertEqual(netplay.stop_lobby.call_count, 2)
                netplay.running_local_lobby.return_value = None
                panel.refresh()
                self.assertTrue(panel.lobby_row.isHidden())
            finally:
                panel.shutdown()
                panel.deleteLater()
        self.run_dialog()

    def test_netplay_config_survives_the_input_editor(self):
        # The joystick mode editor writes "" back for a default mode as
        # the mode moves under it; a player must still end up with the
        # host's value, or their config differs from the host's.
        from fsgs.context import fsgs
        from launcher.launcher_config import LauncherConfig
        from launcher.netplay.config_apply import apply_document
        from launcher.ui.config.InputSelector import InputSelector

        keys = ["amiga_model", "joystick_port_1_mode"]
        doc = {
            "config_version": 1,
            "config": {
                "amiga_model": "A500",
                "joystick_port_1_mode": "joystick",
            },
            "keys": {"sync": keys, "checksum": keys},
        }
        self.setup_dialog()
        with patch.object(fsgs.config, "values", dict(fsgs.config.values)):
            fsgs.config.values.update(
                {"amiga_model": "A500", "joystick_port_1_mode": "nothing"}
            )
            selector = InputSelector(self.dialog, 1)
            try:
                # Without putting the echo back, this is what applying left.
                LauncherConfig.set("joystick_port_1_mode", "nothing")
                LauncherConfig.set("joystick_port_1_mode", "joystick")
                self.assertEqual(fsgs.config.get("joystick_port_1_mode"), "")
                LauncherConfig.set("joystick_port_1_mode", "nothing")

                config_hash, missing = apply_document(doc)
                self.assertEqual(missing, {})
                self.assertEqual(
                    fsgs.config.get("joystick_port_1_mode"), "joystick"
                )
                self.assertEqual(
                    config_hash,
                    LauncherConfig.checksum_config(doc["config"], keys),
                )
            finally:
                selector.on_destroy()
        self.run_dialog()

    def test_netplay_settings_page(self):
        from fsbc.settings import Settings
        from launcher.settings.netplay_settings_page import NetplaySettingsPage

        settings = Settings()
        settings._loaded = True
        settings._atexit_registered = True
        settings.verbose = False
        self.setup_dialog()
        with patch.object(Settings, "_instance", settings):
            page = NetplaySettingsPage(self.dialog)
            try:
                self.assertEqual(
                    page.options_on_page,
                    {
                        "netplay_name",
                        "netplay_tag",
                        "netplay_public_address",
                        "netplay_host_port",
                    },
                )
            finally:
                page.lobby_servers_group.on_destroy()
        self.run_dialog()


class TestDashboard(WidgetTestCase):
    def test_aligned_settings_preserve_values_and_defaults(self):
        from launcher.option import Option
        from launcher.settings.settings_page import SettingsPage

        self.setup_dialog()
        with patch(
            "launcher.settings.option_ui.LauncherSettings.get", return_value=""
        ):
            with patch(
                "launcher.settings.option_ui.app",
                Mock(qapplication=self.application),
            ):
                with patch(
                    "launcher.settings.option_ui.OverrideWarning",
                    side_effect=lambda parent, name: fsui.Label(parent, ""),
                ):
                    page = SettingsPage(self.dialog)
                    text_group = page.add_option("netplay_name")
                    choice_group = page.add_option(Option.LOW_LATENCY_VSYNC)
                    integer_group = page.add_option(Option.LAUNCHER_FONT_SIZE)
        with patch(
            "launcher.settings.option_ui.LauncherSettings.set"
        ) as set_value:
            text_group.value_control.set_text("  Player  ")
            set_value.reset_mock()
            text_group.value_control.on_changed()
            set_value.assert_called_once_with("netplay_name", "Player")
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
            self.assertEqual(
                integer_group.value_control.get_value(),
                Option.get(Option.LAUNCHER_FONT_SIZE)["default"],
            )
            self.assertEqual(
                set_value.call_args.args, (Option.LAUNCHER_FONT_SIZE, "")
            )
        with patch(
            "launcher.settings.settings_page.LauncherSettings.set"
        ) as reset:
            page.reset_to_defaults()
            self.assertEqual(
                {call.args for call in reset.call_args_list},
                {
                    ("netplay_name", ""),
                    (Option.LOW_LATENCY_VSYNC, ""),
                    (Option.LAUNCHER_FONT_SIZE, ""),
                },
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
            for key in (
                Option.JIT_COMPILER,
                Option.FLOPPY_DRIVE_SPEED,
                Option.FLOPPY_DRIVE_VOLUME_EMPTY,
            ):
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
                self.application.setPalette(
                    self.application.style().standardPalette()
                )
                self.application.setFont(font)
                if variant == "modern":
                    apply_modern_theme(self.application)
                elif variant != "plain":
                    apply_retro_theme(self.application, variant)
                for panel_type in (
                    RomRamPanel,
                    ExpansionsPanel,
                    AdditionalConfigPanel,
                ):
                    with self.subTest(
                        theme=variant, panel=panel_type.__name__
                    ), patch.object(fsui, "theme_variant", variant):
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
                                    group = (
                                        panel.memory_group
                                        if isinstance(panel, RomRamPanel)
                                        else panel
                                    )
                                    choices = group.widget().findChildren(
                                        QComboBox
                                    )
                                    self.assertGreater(len(choices), 1)
                                    widths = [
                                        choice.width() for choice in choices
                                    ]
                                    self.assertLessEqual(
                                        max(widths) - min(widths), 1
                                    )
                                    self.assertGreater(min(widths), 75)
                                    controls = (
                                        choices
                                        + group.widget().findChildren(QSpinBox)
                                    )
                                    for control in controls:
                                        self.assertEqual(
                                            control.width(), choices[0].width()
                                        )
                                        self.assertGreaterEqual(control.x(), 0)
                                        self.assertLessEqual(
                                            control.geometry().right(),
                                            control.parentWidget().width(),
                                        )
                                        checkbox = (
                                            control.parentWidget().findChild(
                                                fsui.qt.QCheckBox
                                            )
                                        )
                                        self.assertGreaterEqual(
                                            control.x()
                                            - checkbox.geometry().right()
                                            - 1,
                                            20,
                                        )
                                    if isinstance(panel, RomRamPanel):
                                        roms = panel.kickstart_group
                                        self.assertEqual(
                                            roms.text_field.x(),
                                            roms.ext_text_field.x(),
                                        )
                                        self.assertEqual(
                                            roms.kickstart_type_choice.width(),
                                            roms.ext_rom_type_choice.width(),
                                        )
                        finally:
                            self.run_dialog()
        finally:
            self.application.setPalette(palette)
            self.application.setStyleSheet(stylesheet)
            self.application.setFont(font)

    def test_library_empty_state_and_media_placeholders(self):
        from launcher.ui.ConfigurationsBrowser import ConfigurationsBrowser
        from launcher.ui.floppyselector import FloppySelector

        self.setup_dialog()
        self.dialog.layout = fsui.VerticalLayout()
        item = {
            "uuid": "u1",
            "name": "Test",
            "path": "",
            "have": 4,
            "platform": "Amiga",
            "published": 1,
            "sort_key": "test",
        }
        settings = {"config_search": ""}
        with patch(
            "launcher.ui.ConfigurationsBrowser.Database.get_instance"
        ) as database_factory, patch(
            "launcher.ui.ConfigurationsBrowser.LauncherSettings.get",
            side_effect=lambda key: settings.get(key, ""),
        ), patch(
            "launcher.ui.ConfigurationsBrowser.LauncherSettings.set"
        ) as set_setting, patch(
            "launcher.ui.ConfigurationsBrowser.LauncherSettings.add_listener"
        ), patch(
            "launcher.ui.ConfigurationsBrowser.LauncherSettings.remove_listener"
        ):
            database = database_factory.return_value
            database.find_games_new.return_value = []
            browser = ConfigurationsBrowser(self.dialog)
            self.dialog.layout.add(browser, fill=True, expand=True)
            self.dialog.set_size((540, 300))
            self.dialog.show()
            self.application.processEvents()
            overlay = browser.empty_state
            self.assertFalse(overlay.isHidden())
            self.assertEqual(overlay.title.text(), "No games yet")
            self.assertEqual(overlay.button.text(), "Scan a folder\u2026")
            self.assertEqual(overlay.geometry(), browser.viewport().rect())
            with patch("launcher.ui.scan.ScanDialog") as scan_dialog:
                overlay.button.click()
                scan_dialog.assert_called_once()
                scan_dialog.return_value.show.assert_called_once_with()

            # A search with no hits offers to clear the search instead.
            settings["config_search"] = "zzz"
            browser.update_search()
            self.assertFalse(overlay.isHidden())
            self.assertEqual(
                overlay.title.text(), "Nothing matches your search"
            )
            self.assertEqual(overlay.button.text(), "Clear search")
            overlay.button.click()
            set_setting.assert_called_with("config_search", "")

            # An empty selected list is not an empty library.
            settings["config_search"] = ""
            settings["game_list_uuid"] = "fav"
            browser.update_search()
            self.assertEqual(overlay.title.text(), "This list is empty")
            self.assertNotIn("Scan", overlay.button.text())
            self.assertEqual(overlay.button.text(), "Show Configs and Games")
            overlay.button.click()
            set_setting.assert_called_with("game_list_uuid", "")
            settings["game_list_uuid"] = ""

            # Rows hide the overlay; removing them brings it back.
            settings["config_search"] = ""
            database.find_games_new.return_value = [item]
            browser.update_search()
            self.assertTrue(overlay.isHidden())
            database.find_games_new.return_value = []
            browser.update_search()
            self.assertFalse(overlay.isHidden())

        with patch("launcher.ui.floppyselector.fsgs") as fsgs_mock, patch(
            "launcher.ui.floppyselector.LauncherConfig.get", return_value=""
        ):
            fsgs_mock.config.get.return_value = "amiga"
            first = FloppySelector(self.dialog, 0)
            second = FloppySelector(self.dialog, 1)
            self.assertIn(
                "No disk inserted", first.text_field.placeholderText()
            )
            self.assertEqual(
                second.text_field.placeholderText(), "Empty drive"
            )
            first.set_mode(FloppySelector.CD_MODE)
            self.assertIn("No CD inserted", first.text_field.placeholderText())
        self.run_dialog()

    def test_search_clear_updates_text_field(self):
        from launcher.ui.ConfigurationsPanel import ConfigurationsPanel

        panel = Mock()
        panel.text_field.get_text.return_value = "zzz"
        ConfigurationsPanel.on_setting(panel, "config_search", "")
        panel.text_field.set_text.assert_called_once_with("")
        panel.text_field.set_text.reset_mock()
        panel.text_field.get_text.return_value = "abc"
        ConfigurationsPanel.on_setting(panel, "config_search", "abc")
        panel.text_field.set_text.assert_not_called()

    def test_display_settings_controls_and_fullscreen(self):
        from launcher.launcher_settings import LauncherSettings
        from launcher.panels.displaysettingspanel import DisplaySettingsPanel
        from launcher.settings.option_ui import OptionUI
        from launcher.ui.config.configscrollarea import ConfigScrollArea

        settings = {"fullscreen": "0", "quick_settings_options": "scanlines"}
        listeners = []

        def set_setting(key, value):
            settings[key] = value
            for listener in list(listeners):
                listener.on_setting(key, value)

        self.setup_dialog()
        with patch.object(
            LauncherSettings,
            "get",
            side_effect=lambda key: settings.get(key, ""),
        ), patch.object(
            LauncherSettings, "set", side_effect=set_setting
        ) as write_setting, patch.object(
            LauncherSettings, "add_listener", side_effect=listeners.append
        ), patch.object(
            LauncherSettings, "remove_listener"
        ), patch(
            "launcher.ui.behaviors.configbehavior.LauncherConfig.add_listener"
        ), patch(
            "launcher.ui.behaviors.configbehavior.LauncherConfig.get",
            return_value="",
        ), patch(
            "launcher.launcher_config.LauncherConfig.game_override_identity",
            return_value=("variant_uuid", "game"),
        ), patch(
            "launcher.launcher_config.LauncherConfig.game_overrides_available",
            return_value=True,
        ), patch(
            "launcher.ui.launch.GameDriver.screen_rect_for_monitor",
            return_value=(0, 0, 1920, 1080),
        ), patch(
            "launcher.ui.launch.GameDriver.screen_refresh_rate_for_monitor",
            return_value=60,
        ), patch.object(
            OptionUI, "create_group", wraps=OptionUI.create_group
        ) as create_group:
            area = ConfigScrollArea(self.dialog)
            panel = DisplaySettingsPanel(area)
            area.set_widget(panel)
            self.dialog.layout = fsui.VerticalLayout()
            self.dialog.layout.add(area, fill=True, expand=True)
            self.assertEqual(
                [args[0][1] for args in create_group.call_args_list],
                [
                    "scale",
                    "stretch",
                    "bezel",
                    "zoom",
                    "scanlines",
                    "video_sync",
                ],
            )
            scale = create_group.call_args_list[0].args[0]
            self.assertTrue(scale.is_enabled())
            self.assertFalse(panel.fullscreen_checkbox.is_checked())
            self.assertEqual(panel.screen_info_label.text(), "")
            self.assertTrue(panel.fullscreen_warning.widget().isHidden())
            write_setting.assert_not_called()
            panel.fullscreen_checkbox.click()
            self.assertEqual(settings["fullscreen"], "1")
            self.assertTrue(panel.fullscreen_checkbox.is_checked())
            self.assertIn("1920x1080", panel.screen_info_label.text())
            panel.fullscreen_checkbox.click()
            self.assertEqual(settings["fullscreen"], "0")
            self.assertFalse(panel.fullscreen_checkbox.is_checked())
            self.assertEqual(panel.screen_info_label.text(), "")
            write_setting.reset_mock()
            set_setting("fullscreen", "1")
            self.assertTrue(panel.fullscreen_checkbox.is_checked())
            set_setting("fullscreen", "0")
            self.assertFalse(panel.fullscreen_checkbox.is_checked())
            set_setting("fullscreen", "")
            self.assertFalse(panel.fullscreen_checkbox.is_checked())
            write_setting.assert_not_called()
            self.assertEqual(panel.screen_info_label.text(), "")
            panel.fullscreen_warning.on_config("1")
            self.assertFalse(panel.fullscreen_warning.widget().isHidden())
            panel.fullscreen_warning.on_config("")
            self.assertTrue(panel.fullscreen_warning.widget().isHidden())
            set_setting("g_sync", "1")
            self.assertFalse(panel.video_sync_group.value_control.is_enabled())
            set_setting("video_sync", "1")
            self.assertFalse(panel.video_sync_group.value_control.is_enabled())
            set_setting("g_sync", "")
            self.assertTrue(panel.video_sync_group.value_control.is_enabled())
            self.assertGreater(panel.monitor_choice.count(), 0)
            with patch(
                "launcher.panels.displaysettingspanel.SettingsDialog.open"
            ) as open_settings:
                panel.on_settings_button()
                open_settings.assert_called_once_with(panel.window)
            self.dialog.set_size((420, 360))
            self.dialog.show()
            self.application.processEvents()
            self.assertEqual(panel.fullscreen_checkbox.x(), 10)
            self.assertLessEqual(
                panel.monitor_choice.y() + panel.monitor_choice.height(),
                panel.fullscreen_checkbox.y(),
            )
            self.assertEqual(
                panel.fullscreen_checkbox.x(),
                panel.monitor_choice.x(),
            )
            panel.fullscreen_checkbox.click()
            self.application.processEvents()
            self.assertLessEqual(
                panel.fullscreen_checkbox.y()
                + panel.fullscreen_checkbox.height(),
                panel.screen_info_label.y(),
            )
            self.assertGreater(area.verticalScrollBar().maximum(), 0)
            self.assertEqual(area.horizontalScrollBar().maximum(), 0)
            self.run_dialog()

    def test_display_settings_registered_in_configuration_book(self):
        from launcher.panels.displaysettingspanel import DisplaySettingsPanel
        from launcher.panels.additionalconfigpanel import AdditionalConfigPanel
        from launcher.ui.dashboard import Dashboard
        from launcher.ui.launcherwindow import LauncherWindow

        owner = Mock(books=[None, Mock(), Mock()])
        pages = []

        def register_page(column, content_class, icon_name, title, tooltip=""):
            pages.append(content_class)
            LauncherWindow._add_page(
                owner, owner.books[column], Mock(), icon_name, title, tooltip
            )

        owner.add_page.side_effect = register_page
        owner.add_scroll_page.side_effect = register_page
        LauncherWindow.add_column_content(owner, 2)
        self.assertEqual(len(pages), len(Dashboard.PAGES))
        self.assertIs(pages[-2], DisplaySettingsPanel)
        self.assertIs(pages[-1], AdditionalConfigPanel)
        self.assertEqual(Dashboard.PAGES[-2][0], "Display settings")
        self.assertEqual(Dashboard.PAGES[-1][0], "Advanced")

    def test_play_tile_and_editor_toggle(self):
        from launcher.launcher_settings import LauncherSettings
        from launcher.ui.book import Book
        from launcher.ui.dashboard import Dashboard
        from launcher.ui.play_tile import EDITOR_SETTING

        settings = {
            "config_name": "Lotus Turbo Challenge 2",
            "parent_uuid": "abc",
        }
        listeners = []

        def set_setting(key, value):
            settings[key] = value
            for listener in list(listeners):
                listener.on_setting(key, value)

        def make_owner():
            owner = fsui.Window(None, title="Play tile")
            owner.gsc = object()
            owner.books = [None, Book(owner), Book(owner)]
            owner.books[1].add_page(fsui.Panel(owner.books[1]))
            owner.books[1].set_page(0)
            for _ in Dashboard.PAGES:
                owner.books[2].add_page(fsui.Panel(owner.books[2]))
            owner.screenshots_panel = None
            owner.status_bar = fsui.Panel(owner)
            owner.on_settings_button = Mock()
            return owner

        with patch.object(
            LauncherSettings,
            "get",
            side_effect=lambda key: settings.get(key, ""),
        ), patch.object(
            LauncherSettings, "set", side_effect=set_setting
        ), patch.object(
            LauncherSettings, "add_listener", side_effect=listeners.append
        ), patch.object(
            LauncherSettings, "remove_listener", side_effect=listeners.remove
        ), patch(
            "launcher.ui.behaviors.configbehavior.LauncherConfig.add_listener"
        ), patch(
            "launcher.ui.behaviors.configbehavior.LauncherConfig.get",
            return_value="",
        ):
            owner = make_owner()
            dashboard = Dashboard(owner)
            owner.layout = fsui.VerticalLayout()
            owner.layout.add(dashboard, fill=True, expand=True)
            owner.show()
            tile = dashboard.play_tile
            self.assertEqual(tile.title.toolTip(), "Lotus Turbo Challenge 2")
            self.assertIn("online database", tile.subtitle.text())
            # The title leaves room for the Play button's minimum width.
            settings["config_name"] = "A very long game title " * 12
            tile._name = settings["config_name"]
            tile._update_title()
            reserved = max(
                tile.play_button.minimumWidth(),
                tile.play_button.sizeHint().width(),
            )
            self.assertGreaterEqual(tile.play_button.minimumWidth(), 132)
            self.assertLessEqual(
                tile.title.fontMetrics().horizontalAdvance(tile.title.text()),
                max(160, tile.width() - reserved - 48),
            )
            set_setting("config_name", "Lotus Turbo Challenge 2")
            self.assertEqual(tile.play_button.text(), "Play")
            self.assertTrue(tile.play_button.isEnabled())
            # Editor hidden by default for a clean first impression.
            self.assertFalse(dashboard.edit_toggle.isChecked())
            self.assertTrue(dashboard.editor.isHidden())
            self.assertEqual(
                dashboard.edit_toggle.toolTip(), "Edit configuration"
            )
            self.assertFalse(hasattr(tile, "edit_button"))
            self.assertFalse(hasattr(dashboard, "launch_bar"))
            self.assertFalse(hasattr(dashboard, "quick_toggle"))

            with patch("launcher.launcherapp.LauncherApp.start_game") as start:
                tile.play_button.click()
                start.assert_called_once_with()

            tile.on___running_config("1")
            self.assertFalse(tile.play_button.isEnabled())
            self.assertEqual(tile.play_button.text(), "Running")
            tile.on___progress_config("Preparing: Downloading game (25%)")
            self.assertEqual(
                tile.subtitle.text(), "Preparing: Downloading game (25%)"
            )
            self.assertEqual(tile.subtitle.toolTip(), tile.subtitle.text())
            set_setting("config_path", "/configs/current.fs-uae")
            self.assertEqual(
                tile.subtitle.text(), "Preparing: Downloading game (25%)"
            )
            tile.on___progress_config("Running: Emulator")
            self.assertEqual(tile.subtitle.text(), "Running: Emulator")
            tile.on___running_config("0")
            self.assertTrue(tile.play_button.isEnabled())
            self.assertIn("online database", tile.subtitle.text())
            tile.on___progress_config("Late progress from completed launch")
            self.assertIn("online database", tile.subtitle.text())
            tile.on___running_config("1")
            self.assertNotIn("Late progress", tile.subtitle.text())
            tile.on___progress_config("")
            self.assertIn("online database", tile.subtitle.text())
            tile.on___running_config("0")
            set_setting("config_path", "")

            dashboard.edit_toggle.click()
            self.assertFalse(dashboard.editor.isHidden())
            self.assertEqual(settings[EDITOR_SETTING], "1")
            dashboard.edit_toggle.click()
            self.assertTrue(dashboard.editor.isHidden())
            self.assertEqual(settings[EDITOR_SETTING], "0")

            # Picking a configuration page from the rail reveals the editor.
            dashboard.nav_buttons[3].click()
            self.assertTrue(dashboard.edit_toggle.isChecked())
            self.assertFalse(dashboard.editor.isHidden())
            self.assertIs(owner.books[2].current_page, owner.books[2].pages[3])

            display_index = len(Dashboard.PAGES) - 2
            dashboard.edit_toggle.click()
            dashboard.nav_buttons[display_index].click()
            self.assertEqual(dashboard.page_title.text(), "Display settings")
            self.assertTrue(dashboard.edit_toggle.isChecked())
            self.assertFalse(dashboard.editor.isHidden())
            self.assertFalse(dashboard.library.isHidden())
            self.assertIs(
                owner.books[2].current_page,
                owner.books[2].pages[display_index],
            )

            set_setting("parent_uuid", "")
            set_setting("config_name", "")
            self.assertIn("Amiga 500", tile.title.toolTip())
            self.assertIn("library", tile.subtitle.text())
            # Switching to a saved local configuration updates the hint
            # even though parent_uuid does not change.
            set_setting("config_path", "/configs/mine.fs-uae")
            self.assertIn("saved configuration", tile.subtitle.text())
            set_setting("config_path", "")
            self.assertIn("library", tile.subtitle.text())
            set_setting("config_path", "/configs/mine.fs-uae")
            set_setting("parent_uuid", "abc")
            self.assertIn("online database", tile.subtitle.text())
            set_setting("parent_uuid", "")
            self.assertIn("saved configuration", tile.subtitle.text())
            set_setting("config_path", "")
            owner.closed.emit()
            self.assertNotIn(tile, listeners)

            # The remembered state is restored for the next window.
            owner = make_owner()
            dashboard = Dashboard(owner)
            self.assertTrue(dashboard.edit_toggle.isChecked())
            self.assertFalse(dashboard.editor.isHidden())
            owner.closed.emit()

    def test_plain_language_model_labels(self):
        from fsui.qt import Qt
        from launcher.ui.config.model_labels import (
            MODEL_LABELS,
            VARIANT_LABELS,
            model_label,
            variant_label,
        )
        from launcher.ui.config.modelgroup import ModelGroup
        from fsgs.amiga.amiga import Amiga

        # Every model and variant has an everyday label.
        families = {model["id"].split("/", 1)[0] for model in Amiga.models}
        self.assertEqual(families, set(MODEL_LABELS))
        self.assertEqual(
            {model["id"] for model in Amiga.models}, set(VARIANT_LABELS)
        )
        self.assertEqual(model_label("A500"), "Amiga 500")
        self.assertEqual(model_label("unknown"), "unknown")
        self.assertEqual(
            variant_label("A1200/1230", "x"), "Blizzard 1230 accelerator"
        )
        self.assertEqual(variant_label("unknown", "fallback"), "fallback")
        self.assertNotIn("memory", VARIANT_LABELS["A1200/020"].lower())
        self.assertIn("68020", VARIANT_LABELS["A1200/020"])

        # xgettext only extracts literals passed directly to a keyword.
        import ast
        import inspect
        from launcher.ui.config import model_labels

        tree = ast.parse(inspect.getsource(model_labels))
        marked = {
            node.args[0].value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "N_"
        }
        expected = {text for pair in MODEL_LABELS.values() for text in pair}
        expected |= set(VARIANT_LABELS.values())
        self.assertEqual(expected - marked, set())
        for name in ("MODEL_LABELS", "VARIANT_LABELS"):
            assignment = next(
                node
                for node in tree.body
                if isinstance(node, ast.Assign) and node.targets[0].id == name
            )
            wrapped = {
                id(node.args[0])
                for node in ast.walk(assignment.value)
                if isinstance(node, ast.Call)
            }
            keys = {id(key) for key in assignment.value.keys}
            bare = [
                node.value
                for node in ast.walk(assignment.value)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in wrapped
                and id(node) not in keys
            ]
            self.assertEqual(bare, [])

        self.setup_dialog()
        config = {
            "amiga_model": "",
            "platform": "amiga",
            "accuracy": "",
            "ntsc_mode": "",
        }
        with patch(
            "launcher.ui.config.modelgroup.LauncherConfig.get",
            side_effect=lambda key, default="": config.get(key, default),
        ), patch(
            "launcher.ui.config.modelgroup.LauncherConfig.set"
        ) as set_config, patch(
            "launcher.ui.behaviors.configbehavior.LauncherConfig.get",
            side_effect=lambda key, default="": config.get(key, default),
        ), patch(
            "launcher.ui.behaviors.configbehavior.LauncherConfig.add_listener"
        ), patch(
            "launcher.ui.config.ConfigCheckBox.LauncherConfig.get",
            side_effect=lambda key, default="": config.get(key, default),
        ):
            group = ModelGroup(self.dialog)
            labels = [
                group.model_choice.itemText(i)
                for i in range(group.model_choice.count())
            ]
            self.assertIn("Amiga 500", labels)
            self.assertNotIn("A500", labels)
            self.assertEqual(group.model_choice.currentText(), "Amiga 500")
            tooltip = group.model_choice.itemData(
                labels.index("Amiga 500"), Qt.ItemDataRole.ToolTipRole
            )
            self.assertIn("most games", tooltip)
            self.assertIn("Technical: A500", tooltip)
            self.assertEqual(
                group.sub_model_choice.currentText(),
                "Standard (1 MB total memory)",
            )
            self.assertIn(
                '512 KB "Slow" RAM',
                group.sub_model_choice.itemData(
                    group.sub_model_choice.currentIndex(),
                    Qt.ItemDataRole.ToolTipRole,
                ),
            )
            # Selecting by everyday name still stores the technical id.
            group.model_choice.set_index(group.model_ids.index("A1200"))
            set_config.assert_called_with("amiga_model", "A1200")
            group.on_amiga_model_config("A1200/1230")
            self.assertEqual(group.model_choice.currentText(), "Amiga 1200")
            self.assertEqual(
                group.sub_model_choice.currentText(),
                "Blizzard 1230 accelerator",
            )
            self.assertIn("Blizzard 1230", group.sub_model_choice.toolTip())
            self.assertTrue(group.model_choice.toolTip())
            # Single-variant families have a disabled combo, so the control
            # itself carries the technical details.
            group.on_amiga_model_config("A600")
            self.assertFalse(group.sub_model_choice.is_enabled())
            self.assertIn("Technical:", group.sub_model_choice.toolTip())
            self.assertIn("A600", group.sub_model_choice.toolTip())
            self.assertTrue(group.accuracy_choice.toolTip())
            self.assertTrue(group.ntsc_checkbox.toolTip())
        self.run_dialog()

    def test_ui_scale_slider(self):
        from launcher.launcher_settings import LauncherSettings
        from launcher.option import Option
        from launcher.settings.launchersettingspage import LauncherSettingsPage
        from launcher.settings.ui_scale import UIScaleSlider

        settings = {"launcher_font_size": ""}
        listeners = []

        def set_setting(key, value):
            settings[key] = value
            for listener in list(listeners):
                listener.on_setting(key, value)

        self.setup_dialog()
        application = Mock(qapplication=self.application)
        with patch.object(
            LauncherSettings,
            "get",
            side_effect=lambda key: settings.get(key, ""),
        ), patch.object(
            LauncherSettings, "set", side_effect=set_setting
        ), patch.object(
            LauncherSettings, "add_listener", side_effect=listeners.append
        ), patch.object(
            LauncherSettings, "remove_listener", side_effect=listeners.remove
        ), patch(
            "launcher.settings.option_ui.app", application
        ), patch(
            "launcher.settings.launchersettingspage.app", application
        ), patch(
            "launcher.settings.ui_scale.default_point_size", return_value=12
        ), patch(
            "launcher.settings.launchersettingspage.apply_launcher_theme"
        ):
            page = LauncherSettingsPage(self.dialog)
            slider = page.ui_scale
            self.assertEqual(slider.default, 12)
            self.assertIsInstance(slider, UIScaleSlider)
            self.assertIn(Option.LAUNCHER_FONT_SIZE, page.options_on_page)
            self.assertEqual(slider.value(), slider.default)
            self.assertTrue(slider.caption.text().startswith("Default"))
            self.assertFalse(slider.reset_button.is_enabled())
            self.assertEqual(
                (slider.slider.minimum(), slider.slider.maximum()), (6, 18)
            )
            self.assertEqual(slider.title.text(), "Interface Font Size")
            self.assertEqual(
                slider.slider.accessibleName(), "Interface Font Size"
            )
            self.assertEqual(
                slider.spinbox.accessibleName(), "Interface Font Size"
            )
            self.assertEqual(
                (slider.spinbox.minimum(), slider.spinbox.maximum()), (6, 18)
            )
            self.assertEqual(slider.spinbox.value(), slider.default)
            self.assertEqual(slider.spinbox.suffix(), " pt")

            slider.spinbox.stepUp()
            self.assertEqual(slider.value(), 13)
            self.assertEqual(settings["launcher_font_size"], "13")
            slider.spinbox.stepDown()
            self.assertEqual(slider.value(), 12)
            self.assertEqual(settings["launcher_font_size"], "")
            slider.spinbox.lineEdit().setText("14 pt")
            slider.spinbox.interpretText()
            self.assertEqual(slider.value(), 14)
            self.assertEqual(settings["launcher_font_size"], "14")
            slider.spinbox.setValue(slider.spinbox.minimum())
            slider.spinbox.stepDown()
            self.assertEqual(slider.value(), 6)
            slider.spinbox.setValue(slider.spinbox.maximum())
            slider.spinbox.stepUp()
            self.assertEqual(slider.value(), 18)

            slider.slider.setValue(slider.default + 3)
            self.assertEqual(
                settings["launcher_font_size"], str(slider.default + 3)
            )
            self.assertTrue(slider.caption.text().startswith("Larger"))
            self.assertTrue(slider.reset_button.is_enabled())
            self.assertEqual(slider.spinbox.value(), slider.default + 3)

            # Dragging only commits on release.
            slider.slider.setSliderDown(True)
            slider.slider.setValue(slider.default - 2)
            self.assertEqual(
                settings["launcher_font_size"], str(slider.default + 3)
            )
            self.assertTrue(slider.caption.text().startswith("Smaller"))
            self.assertEqual(slider.spinbox.value(), slider.default - 2)
            slider.slider.setSliderDown(False)
            slider.slider.sliderReleased.emit()
            self.assertEqual(
                settings["launcher_font_size"], str(slider.default - 2)
            )

            slider.reset_button.widget().click()
            self.assertEqual(settings["launcher_font_size"], "")
            self.assertEqual(slider.value(), slider.default)
            self.assertEqual(slider.spinbox.value(), slider.default)

            # External changes (Reset to Defaults, other pages) move the slider.
            set_setting("launcher_font_size", "16")
            self.assertEqual(slider.value(), 16)
            self.assertEqual(slider.spinbox.value(), 16)
            set_setting("launcher_font_size", "garbage")
            self.assertEqual(slider.value(), slider.default)
            self.assertEqual(slider.spinbox.value(), slider.default)
            set_setting("launcher_font_size", "99")
            self.assertEqual(slider.value(), 18)
            self.assertEqual(slider.spinbox.value(), 18)
            page.reset_to_defaults()
            self.assertEqual(settings["launcher_font_size"], "")
            self.assertEqual(slider.value(), slider.default)
        self.run_dialog()

    def test_ui_scale_default_follows_theme_and_clamps(self):
        from fsui.qt.qt import apply_launcher_theme, theme_default_point_size
        from launcher.launcher_settings import LauncherSettings
        from launcher.settings.ui_scale import UIScaleSlider

        palette = self.application.palette()
        stylesheet = self.application.styleSheet()
        font = self.application.font()
        state = fsui.theme, fsui.theme_variant, fsui.theme_skin
        settings = {"launcher_font_size": "", "launcher_theme": "fusion-plain"}
        listeners = []

        def set_setting(key, value):
            settings[key] = value
            for listener in list(listeners):
                listener.on_setting(key, value)

        self.setup_dialog()
        try:
            with patch.object(
                LauncherSettings,
                "get",
                side_effect=lambda key: settings.get(key, ""),
            ), patch.object(
                LauncherSettings, "set", side_effect=set_setting
            ), patch.object(
                LauncherSettings, "add_listener", side_effect=listeners.append
            ), patch.object(
                LauncherSettings,
                "remove_listener",
                side_effect=listeners.remove,
            ):
                system = Mock(return_value=QFont("DejaVu Sans", 9))
                with patch("fsui.qt.qt.QFontDatabase.systemFont", system):
                    apply_launcher_theme(self.application, "fusion-plain", "")
                    slider = UIScaleSlider(self.dialog)
                    self.assertEqual(slider.default, 9)
                    modern = theme_default_point_size("fusion-modern")
                    apply_launcher_theme(self.application, "fusion-modern", "")
                    self.assertEqual(slider.default, modern)
                    self.assertEqual(slider.value(), modern)

                    # With a modern 10 pt default, 9 pt is an explicit choice.
                    if modern == 10:
                        slider.slider.setValue(9)
                        self.assertEqual(settings["launcher_font_size"], "9")

                    # An override equal to the default can still be cleared.
                    set_setting("launcher_font_size", str(slider.default))
                    self.assertTrue(slider.reset_button.is_enabled())
                    slider.slider.setValue(slider.default)
                    slider.reset_button.widget().click()
                    self.assertEqual(settings["launcher_font_size"], "")
                    self.assertFalse(slider.reset_button.is_enabled())

                    # Boundary defaults clamp into the slider range.
                    with patch(
                        "launcher.settings.ui_scale.default_point_size",
                        return_value=30,
                    ):
                        slider.refresh_default()
                        self.assertEqual(slider.default, 18)
                        slider.slider.setValue(18)
                        self.assertEqual(settings["launcher_font_size"], "")
                        slider.slider.setValue(17)
                        self.assertEqual(settings["launcher_font_size"], "17")
                slider.on_destroy()
        finally:
            self.application.setPalette(palette)
            self.application.setStyleSheet(stylesheet)
            self.application.setFont(font)
            fsui.theme, fsui.theme_variant, fsui.theme_skin = state
        self.run_dialog()

    def test_live_theme_preview(self):
        from fsui.qt import QPalette, modern_theme
        from fsui.qt.qt import theme_applied
        from launcher.launcher_settings import LauncherSettings
        from launcher.netplay.lobby_browser import LobbyBrowser
        from launcher.netplay.lobby_browser_panel import LobbyBrowserPanel
        from launcher.settings.launchersettingspage import LauncherSettingsPage
        from launcher.ui.book import Book
        from launcher.ui.dashboard import Dashboard

        palette = self.application.palette()
        stylesheet = self.application.styleSheet()
        font = self.application.font()
        state = fsui.theme, fsui.theme_variant, fsui.theme_skin
        settings = {
            "launcher_theme": "fusion-modern",
            "launcher_font_size": "",
        }
        listeners = []

        def set_setting(key, value):
            settings[key] = value
            for listener in list(listeners):
                listener.on_setting(key, value)

        self.setup_dialog()
        application = Mock(qapplication=self.application)
        try:
            with patch.object(
                LauncherSettings,
                "get",
                side_effect=lambda key: settings.get(key, ""),
            ), patch.object(
                LauncherSettings, "set", side_effect=set_setting
            ), patch.object(
                LauncherSettings, "add_listener", side_effect=listeners.append
            ), patch.object(
                LauncherSettings,
                "remove_listener",
                side_effect=listeners.remove,
            ), patch(
                "launcher.settings.option_ui.app", application
            ), patch(
                "launcher.settings.launchersettingspage.app", application
            ):
                modern_theme.apply_modern_theme(self.application, "modern")
                fsui.theme_variant, fsui.theme_skin = "modern", "modern"
                owner = fsui.Window(None, title="Preview")
                owner.gsc = object()
                owner.books = [None, Book(owner), Book(owner)]
                owner.books[1].add_page(fsui.Panel(owner.books[1]))
                owner.books[1].set_page(0)
                for _ in Dashboard.PAGES:
                    owner.books[2].add_page(fsui.Panel(owner.books[2]))
                owner.screenshots_panel = None
                owner.status_bar = fsui.Panel(owner)
                owner.on_settings_button = Mock()
                dashboard = Dashboard(owner)
                netplay = Mock(
                    browser_listeners=[],
                    activity_listeners=[],
                    session_listeners=[],
                    activity_log=[],
                    session=None,
                    joining=None,
                )
                netplay.running_local_lobby.return_value = None
                netplay.browser = LobbyBrowser(
                    name=lambda: "Paul",
                    dispatch=lambda f, *a: f(*a),
                )
                details = LobbyBrowserPanel(netplay)
                page = LauncherSettingsPage(self.dialog)
                self.assertIn(
                    "previewed immediately", page.preview_label._widget.text()
                )
                self.assertIn(
                    modern_theme.MODERN.window, dashboard.widget().styleSheet()
                )

                for theme, skin in (
                    ("fusion-hologram", "hologram"),
                    ("fusion-terminal", "terminal"),
                ):
                    with self.subTest(theme=theme):
                        set_setting("launcher_theme", theme)
                        expected = modern_theme.SKINS[skin]
                        self.assertEqual(fsui.theme_skin, skin)
                        self.assertEqual(
                            self.application.palette()
                            .color(QPalette.ColorRole.Window)
                            .name(),
                            expected.window,
                        )
                        self.assertIn(
                            expected.window, dashboard.widget().styleSheet()
                        )
                        self.assertIn(expected.surface, details.styleSheet())
                        self.assertNotIn(
                            modern_theme.MODERN.window,
                            dashboard.widget().styleSheet(),
                        )
                        icon = (
                            dashboard.nav_buttons[0]
                            .icon()
                            .pixmap(20, 20)
                            .toImage()
                        )
                        self.assertFalse(icon.isNull())

                set_setting("launcher_theme", "fusion-windows311")
                self.assertEqual(fsui.theme_variant, "windows311")
                self.assertEqual(
                    self.application.palette()
                    .color(QPalette.ColorRole.Window)
                    .name(),
                    "#c0c0c0",
                )
                self.assertIn(
                    "palette(window)", dashboard.widget().styleSheet()
                )
                self.assertIn("palette(window)", details.styleSheet())

                set_setting("launcher_font_size", "14")
                self.assertEqual(self.application.font().pointSize(), 14)
                set_setting("launcher_font_size", "")
                self.assertNotEqual(self.application.font().pointSize(), 14)

                # Unrelated settings do not re-apply the theme.
                with patch(
                    "launcher.settings.launchersettingspage.apply_launcher_theme"
                ) as apply_theme:
                    set_setting("netplay_name", "Player")
                    apply_theme.assert_not_called()

                # Destroyed widgets stop listening and never break later changes.
                details.shutdown()
                owner.closed.emit()
                set_setting("launcher_theme", "fusion-modern")
                self.assertIn(
                    "palette(window)", dashboard.widget().styleSheet()
                )
                self.assertEqual(fsui.theme_skin, "modern")
                self.assertNotIn(
                    dashboard.restyle, [ref() for ref in theme_applied._refs]
                )
        finally:
            theme_applied._refs = []
            modern_theme.apply_modern_theme(self.application, "modern")
            self.application.setPalette(palette)
            self.application.setStyleSheet(stylesheet)
            self.application.setFont(font)
            fsui.theme, fsui.theme_variant, fsui.theme_skin = state
        self.run_dialog()

    def test_font_preview_keeps_command_line_theme_and_relayouts(self):
        from fsui.qt import modern_theme
        from fsui.qt.qt import apply_launcher_theme, theme_applied
        from launcher.launcher_settings import LauncherSettings
        from launcher.settings.launchersettingspage import LauncherSettingsPage

        palette = self.application.palette()
        stylesheet = self.application.styleSheet()
        font = self.application.font()
        state = fsui.theme, fsui.theme_variant, fsui.theme_skin
        settings = {"launcher_theme": "fusion-plain", "launcher_font_size": ""}
        listeners = []

        def set_setting(key, value):
            settings[key] = value
            for listener in list(listeners):
                listener.on_setting(key, value)

        self.setup_dialog()
        application = Mock(qapplication=self.application)
        try:
            with patch.object(
                LauncherSettings,
                "get",
                side_effect=lambda key: settings.get(key, ""),
            ), patch.object(
                LauncherSettings, "set", side_effect=set_setting
            ), patch.object(
                LauncherSettings, "add_listener", side_effect=listeners.append
            ), patch.object(
                LauncherSettings,
                "remove_listener",
                side_effect=listeners.remove,
            ), patch(
                "launcher.settings.option_ui.app", application
            ), patch(
                "launcher.settings.launchersettingspage.app", application
            ):
                apply_launcher_theme(self.application, "fusion-cyberpunk", "")
                page = LauncherSettingsPage(self.dialog)
                self.assertEqual(fsui.theme_skin, "cyberpunk")

                set_setting("launcher_font_size", "12")
                self.assertEqual(fsui.theme_skin, "cyberpunk")
                self.assertEqual(self.application.font().pointSize(), 12)

                set_setting("launcher_theme", "fusion-plain")
                self.assertEqual(fsui.theme_variant, "plain")

                layouts = [
                    group.label_layout
                    for group in page.option_groups
                    if hasattr(group, "label_layout")
                ]
                self.assertTrue(layouts)
                set_setting("launcher_font_size", "8")
                small = layouts[0].min_width
                set_setting("launcher_font_size", "24")
                large = layouts[0].min_width
                self.assertGreater(large, small)
                self.assertEqual(
                    {layout.min_width for layout in layouts}, {large}
                )
            self.run_dialog()
        finally:
            theme_applied._refs = []
            modern_theme.apply_modern_theme(self.application, "modern")
            self.application.setPalette(palette)
            self.application.setStyleSheet(stylesheet)
            self.application.setFont(font)
            fsui.theme, fsui.theme_variant, fsui.theme_skin = state

    def test_font_change_reruns_fsui_layouts(self):
        from fsui.qt import modern_theme
        from fsui.qt.qt import apply_launcher_theme

        palette = self.application.palette()
        stylesheet = self.application.styleSheet()
        font = self.application.font()
        state = fsui.theme, fsui.theme_variant, fsui.theme_skin
        try:
            apply_launcher_theme(self.application, "fusion-plain", "8")
            self.setup_dialog()
            panel = fsui.Panel(self.dialog)
            panel.layout = fsui.VerticalLayout()
            label = fsui.Label(panel, "A fairly long label for measuring")
            panel.layout.add(label)
            self.dialog.layout = fsui.VerticalLayout()
            self.dialog.layout.add(panel, fill=True, expand=True)
            self.dialog.set_size((900, 400))
            self.dialog.show()
            self.application.processEvents()
            before = label.height()
            apply_launcher_theme(self.application, "fusion-plain", "24")
            self.assertGreater(label.height(), before)
            self.assertGreaterEqual(
                label.height(), label.minimumSizeHint().height()
            )
            self.dialog.close()
        finally:
            modern_theme.apply_modern_theme(self.application, "modern")
            self.application.setPalette(palette)
            self.application.setStyleSheet(stylesheet)
            self.application.setFont(font)
            fsui.theme, fsui.theme_variant, fsui.theme_skin = state
        self.run_dialog()

    def test_paged_dialog_navigation_follows_font_and_theme(self):
        from fsui.qt import QFont, modern_theme
        from fsui.qt.qt import apply_launcher_theme
        from launcher.ui.pageddialog import PagedDialog

        palette = self.application.palette()
        stylesheet = self.application.styleSheet()
        font = self.application.font()
        state = fsui.theme, fsui.theme_variant, fsui.theme_skin
        try:
            apply_launcher_theme(self.application, "fusion-modern", "10")
            self.setup_dialog()
            paged = PagedDialog(self.dialog, "Navigation")
            paged.add_page(
                "Common", lambda parent: fsui.Panel(parent), bold=True
            )
            paged.add_page("Other", lambda parent: fsui.Panel(parent))
            model = paged.list_view.model()
            self.assertEqual(model.item(0).sizeHint().height(), 42)
            apply_launcher_theme(self.application, "fusion-workbench", "20")
            first, second = model.item(0), model.item(1)
            self.assertEqual(first.sizeHint().height(), 44)
            self.assertEqual(first.font().pointSize(), 20)
            self.assertGreaterEqual(first.font().weight(), QFont.Weight.Bold)
            self.assertLess(second.font().weight(), QFont.Weight.Bold)
            self.assertEqual(second.font().pointSize(), 20)
            apply_launcher_theme(self.application, "fusion-modern", "10")
            self.assertEqual(model.item(0).sizeHint().height(), 42)
            self.assertEqual(model.item(0).font().pointSize(), 10)
            paged.close()
        finally:
            modern_theme.apply_modern_theme(self.application, "modern")
            self.application.setPalette(palette)
            self.application.setStyleSheet(stylesheet)
            self.application.setFont(font)
            fsui.theme, fsui.theme_variant, fsui.theme_skin = state
        self.run_dialog()

    def test_restart_button_confirmation(self):
        from fsui.qt import QMessageBox
        from launcher.settings.launchersettingspage import LauncherSettingsPage

        self.setup_dialog()
        application = Mock(qapplication=self.application)
        with patch("launcher.settings.option_ui.app", application):
            with patch(
                "launcher.settings.launchersettingspage.app", application
            ):
                page = LauncherSettingsPage(self.dialog)
                self.assertFalse(page.restart_button.widget().icon().isNull())
                with patch(
                    "fsui.qt.QMessageBox.question",
                    return_value=QMessageBox.StandardButton.No,
                ):
                    page.restart_button.widget().click()
                    application.request_restart.assert_not_called()
                with patch(
                    "fsui.qt.QMessageBox.question",
                    return_value=QMessageBox.StandardButton.Yes,
                ):
                    page.restart_button.widget().click()
                    application.request_restart.assert_called_once_with()
                application.request_restart.side_effect = OSError("Disk full")
                with patch(
                    "fsui.qt.QMessageBox.question",
                    return_value=QMessageBox.StandardButton.Yes,
                ):
                    with patch("fsui.show_error") as show_error:
                        page.restart_button.widget().click()
                        show_error.assert_called_once()
        self.run_dialog()

    def test_portable_mode_confirmation_and_cancellation(self):
        from fsui.qt import QMessageBox
        from launcher.settings.launchersettingspage import LauncherSettingsPage

        self.setup_dialog()
        application = Mock(qapplication=self.application)
        # Leaving portable mode is refused while FS_UAE_BASE_DIR overrides
        # the data folder, as it does for the test run (conftest.py).
        environ = {
            k: v for k, v in os.environ.items() if k != "FS_UAE_BASE_DIR"
        }
        with patch.dict(os.environ, environ, clear=True), patch(
            "launcher.settings.option_ui.app", application
        ), patch(
            "launcher.settings.launchersettingspage.app", application
        ), patch(
            "fsboot.is_portable", return_value=False
        ), patch(
            "launcher.portable.PortableModeChange"
        ) as change_class, patch(
            "launcher.scanner.Scanner.running", False
        ):
            page = LauncherSettingsPage(self.dialog)
            self.assertFalse(page.portable_checkbox.is_checked())
            self.assertFalse(page.portable_folder_button.is_enabled())
            with patch("fsui.pick_directory", return_value=""):
                page.portable_checkbox.click()
            application.request_restart.assert_not_called()
            self.assertFalse(page.portable_checkbox.is_checked())
            with patch(
                "fsui.pick_directory", return_value="/example/portable"
            ):
                with patch(
                    "fsui.qt.QMessageBox.question",
                    return_value=QMessageBox.StandardButton.No,
                ):
                    page.portable_checkbox.click()
                application.request_restart.assert_not_called()
                with patch(
                    "fsui.qt.QMessageBox.question",
                    return_value=QMessageBox.StandardButton.Yes,
                ):
                    page.portable_checkbox.click()
                application.request_restart.assert_called_once_with(
                    portable_change=change_class.return_value
                )
            self.assertFalse(page.portable_checkbox.is_checked())
            application.request_restart.reset_mock()
            with patch("fsboot.is_portable", return_value=True):
                page.reset_portable_checkbox()
                with patch(
                    "fsui.pick_directory", return_value="/example/normal"
                ), patch(
                    "fsui.qt.QMessageBox.question",
                    return_value=QMessageBox.StandardButton.Yes,
                ):
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
                with self.subTest(variant=variant), patch.object(
                    fsui, "theme_variant", variant
                ):
                    if variant == "modern":
                        apply_modern_theme(self.application)
                    elif variant == "plain":
                        self.application.setStyleSheet("")
                        self.application.setPalette(
                            self.application.style().standardPalette()
                        )
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
            "launcher.settings.option_ui.app",
            Mock(qapplication=self.application),
        ):
            with patch(
                "launcher.settings.settings_dialog.LauncherSettings.set"
            ):
                with patch(
                    "launcher.settings.settings_dialog.LauncherSignal.broadcast"
                ):
                    window = SettingsDialog(None)
                    try:
                        window.show()
                        for title in (
                            "WHDLoad",
                            "Audio",
                            "Keyboard",
                            "WHDLoad",
                        ):
                            index = window.set_page_by_title(title)
                            self.application.processEvents()
                            self.assertEqual(window.get_index(), index)
                            self.assertIs(window.page, window.pages[index])
                            self.assertFalse(window.page.widget().isHidden())
                            self.assertIsNone(
                                window.page.icon_header.image_view
                            )
                            self.assertEqual(
                                window.page.icon_header.title_label.font().pixelSize(),
                                25,
                            )
                        for index in range(len(window.pages)):
                            item = window.list_view.model().item(index)
                            self.assertFalse(item.icon().isNull())
                            expected_height = (
                                42 if fsui.theme_variant == "modern" else 44
                            )
                            self.assertEqual(
                                item.sizeHint().height(), expected_height
                            )
                        for width in (1000, 1280):
                            window.set_size((width, 760))
                            for index in range(len(window.pages)):
                                title = window.get_page_title(index)
                                with self.subTest(
                                    theme=fsui.theme_variant,
                                    page=title,
                                    width=width,
                                ):
                                    window.set_page_by_title(title)
                                    self.application.processEvents()
                                    groups = getattr(
                                        window.page, "option_groups", []
                                    )
                                    fields = []
                                    help_positions = []
                                    for group in groups:
                                        control = group.value_control
                                        control = getattr(
                                            control, "_widget", control
                                        )
                                        self.assertGreater(control.width(), 60)
                                        self.assertLessEqual(
                                            control.geometry().right(),
                                            control.parentWidget().width(),
                                        )
                                        help_button = (
                                            group.help_button.widget()
                                        )
                                        self.assertLess(
                                            control.geometry().right(),
                                            help_button.x(),
                                        )
                                        help_positions.append(help_button.x())
                                        if not hasattr(
                                            group, "default_checkbox"
                                        ):
                                            fields.append(
                                                (control.x(), control.width())
                                            )
                                        if hasattr(group, "label_layout"):
                                            self.assertGreaterEqual(
                                                control.x()
                                                - group.label_layout.get_min_width(),
                                                20,
                                            )
                                    self.assertLessEqual(len(set(fields)), 1)
                                    self.assertLessEqual(
                                        len(set(help_positions)), 1
                                    )
                        colors = {
                            "modern": "#9bcce2",
                            "windows311": "#183867",
                            "workbench": "#0055aa",
                            "plain": "#000000",
                        }
                        icons.assert_any_call(
                            "fa5s.globe", color=colors[fsui.theme_variant]
                        )
                        icons.assert_any_call(
                            "fa5s.hdd", color=colors[fsui.theme_variant]
                        )
                        if fsui.theme_variant != "modern":
                            self.assertEqual(
                                window.list_view.iconSize().width(),
                                20 if fsui.theme_variant == "plain" else 24,
                            )
                            self.assertIn(
                                "palette(highlight)",
                                window.list_view.styleSheet(),
                            )
                            self.assertNotIn(
                                "#1c1e2b", window.list_view.styleSheet()
                            )
                    finally:
                        window.close()
                        window.real_window().deleteLater()
                        self.application.sendPostedEvents(
                            None, QEvent.Type.DeferredDelete
                        )

    def test_modern_theme_option(self):
        from launcher.option import Option
        from launcher.settings.option_ui import OptionUI

        self.setup_dialog()
        with patch(
            "launcher.settings.option_ui.LauncherSettings.get", return_value=""
        ):
            group = OptionUI.create_group(
                self.dialog, Option.LAUNCHER_THEME, help_button=False
            )
        labels = [
            group.widget.itemText(index)
            for index in range(group.widget.count())
        ]
        self.assertIn("Modern Dark", labels)
        self.assertEqual(labels[0], "Modern Dark (*)")
        self.assertEqual(labels.count("Windows 3.11"), 1)
        self.assertEqual(labels.count("Amiga Workbench 1.3"), 1)
        self.assertEqual(
            labels,
            [
                "Modern Dark (*)",
                "Modern Dark",
                "Neon City",
                "Synthwave Sunset",
                "Holo Grid",
                "Phosphor Terminal",
                "Fusion",
                "Windows 3.11",
                "Amiga Workbench 1.3",
            ],
        )
        self.run_dialog()

    def test_navigation_and_responsive_layout(self):
        from fsui.qt import modern_theme
        from fsui.qt.modern_theme import apply_modern_theme
        from fsui.qt.retro_theme import apply_retro_theme

        palette = self.application.palette()
        stylesheet = self.application.styleSheet()
        font = self.application.font()
        skin_state = fsui.theme_skin
        try:
            for variant in (
                "modern",
                "plain",
                "windows311",
                "workbench",
                "modern:cyberpunk",
                "modern:synthwave",
                "modern:hologram",
                "modern:terminal",
            ):
                variant, _, skin = variant.partition(":")
                with self.subTest(variant=variant, skin=skin):
                    with patch.object(
                        fsui, "theme_variant", variant
                    ), patch.object(fsui, "theme_skin", skin):
                        if variant == "modern":
                            apply_modern_theme(
                                self.application, skin or "modern"
                            )
                        elif variant == "plain":
                            self.application.setStyleSheet("")
                            self.application.setPalette(
                                self.application.style().standardPalette()
                            )
                        else:
                            apply_retro_theme(self.application, variant)
                        self._check_navigation_and_responsive_layout()
        finally:
            modern_theme.apply_modern_theme(self.application, "modern")
            self.application.setPalette(palette)
            self.application.setStyleSheet(stylesheet)
            self.application.setFont(font)
            fsui.theme_skin = skin_state

    def _check_navigation_and_responsive_layout(self):
        from launcher.ui.book import Book
        from launcher.ui.dashboard import Dashboard

        owner = fsui.Window(None, title="Dashboard test")
        owner.gsc = object()
        owner.books = [None, Book(owner), Book(owner)]
        owner.books[1].add_page(fsui.Panel(owner.books[1]))
        owner.books[1].set_page(0)
        for _ in Dashboard.PAGES:
            panel = fsui.Panel(owner.books[2])
            panel.layout = fsui.VerticalLayout()
            panel.layout.add_spacer(400, 200)
            owner.books[2].add_page(panel)
        owner.screenshots_panel = fsui.Panel(owner)
        owner.game_info_panel = fsui.Panel(owner)
        owner.status_bar = fsui.Panel(owner)
        owner.on_net_play = Mock()
        owner.on_settings_button = Mock()

        with patch("launcher.ui.play_tile.ConfigBehavior"):
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
                    self.assertFalse(dashboard.library.isHidden())
                dashboard.library_toggle.click()
                self.assertTrue(dashboard.library.isHidden())
                dashboard.library_toggle.click()
                self.assertFalse(dashboard.library.isHidden())
                dashboard.edit_toggle.click()
                self.assertTrue(dashboard.editor.isHidden())
                dashboard.edit_toggle.click()
                self.assertFalse(dashboard.editor.isHidden())
                with patch(
                    "launcher.netplay.netplay.Netplay.start_browsing"
                ) as browse:
                    with patch("launcher.netplay.netplay.ConnectionTester"):
                        dashboard.netplay_button.click()
                        page = dashboard.netplay_page
                        self.assertIs(
                            dashboard.content_stack.currentWidget(),
                            page.widget(),
                        )
                        self.assertIs(
                            page.browser_panel.window(), owner.real_window()
                        )
                        self.assertFalse(
                            page.browser_panel.info_button.isHidden()
                        )
                        with patch(
                            "launcher.ui.InfoDialog.InfoDialog"
                        ) as info:
                            page.browser_panel.info_button.click()
                            info.assert_called_once_with(page)
                        if fsui.theme_variant != "modern":
                            self.assertNotIn(
                                "#212431", page.browser_panel.styleSheet()
                            )
                            self.assertNotIn(
                                "#171923", dashboard.widget().styleSheet()
                            )
                        self.assertTrue(dashboard.netplay_button.isChecked())
                        self.assertFalse(dashboard.edit_toggle.isEnabled())
                        self.assertFalse(dashboard.library_toggle.isEnabled())
                        page.netplay.activity("Persistent line")
                        dashboard.nav_buttons[0].click()
                        self.assertIs(
                            dashboard.content_stack.currentWidget(),
                            dashboard.workspace,
                        )
                        self.assertTrue(dashboard.edit_toggle.isEnabled())
                        dashboard.netplay_button.click()
                        self.assertIs(dashboard.netplay_page, page)
                        self.assertIn(
                            "Persistent line",
                            page.browser_panel.activity.toPlainText(),
                        )
                        browse.assert_called_once_with()
                        from launcher.ui.launcherwindow import LauncherWindow

                        owner.dashboard = dashboard
                        with patch(
                            "launcher.netplay.netplay_page.NetplayPage"
                        ) as new_page:
                            LauncherWindow.on_net_play(owner)
                            new_page.assert_not_called()
                        # Closing the window stops the lobby on this computer.
                        server = Mock(process=None)
                        page.netplay.local_lobby = server
                        owner.close()
                        server.stop.assert_called_once_with()
