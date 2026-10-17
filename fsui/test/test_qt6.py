import os
import unittest
from unittest.mock import Mock, patch

import fsui
from fsui.qt import QDialog, QFontMetrics, QImage, QPainter, QTimer
from fsui.qt.DrawingContext import DrawingContext
from fsui.qt.qt import configure_qt_environment
from .WidgetTestCase import WidgetTestCase


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


class TestDashboard(WidgetTestCase):
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
        self.run_dialog()

    def test_navigation_and_responsive_layout(self):
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
                owner.close()