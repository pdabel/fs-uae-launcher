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

    def test_embedded_host_server_lifecycle(self):
        from launcher.netplay.netplay import Netplay
        from launcher.netplay.server_details import ServerDetails

        for action in ("stop", "reset", "disconnect"):
            with self.subTest(action=action):
                view = ServerDetails()
                parent = Mock(create_server_view=view.present)
                netplay = Netplay(parent=parent)
                netplay.irc.active_channel_name = "#embedded-game"
                netplay._hostgame_port = 25101
                netplay._hostgame_attempt = 1
                netplay._hostgame_max_retries = 5
                netplay._hostgame_backoff_base = 5
                netplay._hostgame_players = 2
                netplay._hostgame_password = ""
                netplay._hostgame_addresses = "127.0.0.1"
                netplay._hostgame_channel = Mock()
                try:
                    with patch.object(netplay, "is_port_free", return_value=True):
                        with patch("launcher.netplay.netplay.Server") as server_class:
                            with patch("launcher.netplay.netplay.LauncherConfig.set_multiple"):
                                with patch.object(view, "show", wraps=view.show) as show_view:
                                    server = server_class.return_value
                                    server.players = 2
                                    server.process = None
                                    netplay._hostgame_retry()
                                    server.start.assert_called_once_with()
                                    show_view.assert_called_once_with()
                                    self.assertIs(netplay.game_window, view)
                                    self.assertEqual(view.fields["port"].text(), "25101")
                                    self.assertEqual(view.fields["players"].text(), "2")
                                    self.assertEqual(view.fields["channel"].text(), "#embedded-game")
                                    self.assertTrue(view.fields["game_id"].text())
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
                    irc.irc_join("ReplayUser!user@localhost", "#replay-game")
                    self.assertFalse(panel.netplay.is_op())
                    irc.irc_namreply(
                        "server", "ReplayUser", "=", "#replay-game",
                        "@ReplayUser",
                    )
                    self.application.processEvents()
                    self.assertTrue(panel.netplay.is_op())
                    self.assertEqual(panel.nick_list.get_item(0), "@ReplayUser")
                    self.assertIn("You are the Operator", panel.text_area.get_text())
                    for control in (
                        panel.host_game_button, panel.send_config_button,
                        panel.reset_button, panel.start_button,
                    ):
                        self.assertTrue(control.visible())
                        self.assertGreater(control.widget().geometry().y(), 0)
                    self.assertFalse(panel.ready_button.visible())
                    irc.irc_mode("server", "#replay-game", "-o", "ReplayUser")
                    self.assertFalse(panel.netplay.is_op())
                    self.assertFalse(panel.host_game_button.visible())
                    self.assertTrue(panel.ready_button.visible())
                    irc.irc_mode("server", "#replay-game", "+o", "ReplayUser")
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
                    panel.host_game_button, panel.send_config_button,
                    panel.reset_button, panel.start_button,
                ):
                    self.assertTrue(control.visible())
                    geometry = control.widget().geometry()
                    self.assertGreater(geometry.y(), 0)
                    self.assertLessEqual(geometry.right(), panel.size()[0])
                    if previous is not None:
                        self.assertFalse(previous.intersects(geometry))
                    previous = geometry
                self.assertFalse(panel.ready_button.visible())
                panel.host_game_button.widget().click()
                netplay.handle_command.assert_called_with(
                    "/hostgame 127.0.0.1:25101 2"
                )
                panel.send_config_button.widget().click()
                netplay.handle_command.assert_called_with("/sendconfig")
                panel.reset_button.widget().click()
                netplay.handle_command.assert_called_with("/reset")
                with patch("launcher.launcherapp.LauncherApp.start_game") as start:
                    panel.start_button.widget().click()
                    start.assert_called_once_with()
                netplay.is_op.return_value = False
                panel.on_irc("nick_list", {"channel": "#test-game"})
                self.assertFalse(panel.host_game_button.visible())
                self.assertTrue(panel.ready_button.visible())
                self.assertGreater(panel.ready_button.widget().geometry().y(), 0)
                panel.ready_button.widget().click()
                netplay.handle_command.assert_called_with("/ready")
                panel.set_active_channel(LOBBY_CHANNEL)
                self.assertFalse(panel.ready_button.visible())
                self.assertFalse(panel.host_game_button.visible())
            finally:
                window.close()


class TestDashboard(WidgetTestCase):
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