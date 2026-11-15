import traceback

import fsui
from fsgs.option import Option
from launcher.i18n import gettext
from launcher.launcher_config import LauncherConfig
from launcher.launcher_settings import LauncherSettings
from launcher.option import options
from launcher.settings.monitorbutton import MonitorChoice
from launcher.settings.option_ui import OptionUI
from launcher.settings.override_warning import OverrideWarning
from launcher.settings.settings_dialog import SettingsDialog
from launcher.ui.IconButton import IconButton
from launcher.ui.launch import ScreenInfoLabel
from launcher.ui.behaviors.configbehavior import ConfigBehavior
from launcher.ui.behaviors.platformbehavior import (
    PlatformShowBehavior,
    AMIGA_PLATFORMS,
    PlatformEnableBehavior,
)
from launcher.ui.behaviors.settingsbehavior import SettingsBehavior


class DisplaySettingsPanel(fsui.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self.layout = fsui.VerticalLayout()

        hori_layout = fsui.HorizontalLayout()
        self.layout.add(hori_layout, fill=True)
        heading_label = fsui.HeadingLabel(self, gettext("Display settings"))
        hori_layout.add(heading_label, margin=10)
        hori_layout.add_spacer(0, expand=True)
        settings_button = IconButton(self, "16x16/more.png")
        settings_button.activated.connect(self.on_settings_button)
        hori_layout.add(settings_button, margin_right=10)
        self.layout.add_spacer(0)

        self.add_option(
            Option.SCALE, text=None, enable=AMIGA_PLATFORMS, per_game=True
        )
        self.add_option(
            Option.STRETCH, text=None, enable=AMIGA_PLATFORMS, per_game=True
        )
        self.add_option(
            Option.BEZEL, text=None, enable=AMIGA_PLATFORMS, per_game=True
        )
        self.add_option(
            Option.ZOOM, text=None, platforms=AMIGA_PLATFORMS, per_game=True
        )

        quick_settings = LauncherSettings.get(Option.QUICK_SETTINGS_OPTIONS)
        for option in quick_settings.split(","):
            option = option.strip().lower()
            if "[" in option:
                # For future use of e.g.:
                # option1[platform1,platform2],option2[platform,...]
                option = option.split("[", 1)[0]
            if (
                option in options
                and option
                not in {
                    Option.BEZEL,
                    Option.G_SYNC,
                    Option.MONITOR,
                    Option.SCALE,
                    Option.STRETCH,
                    Option.VIDEO_SYNC,
                    Option.ZOOM,
                }
                and option not in LauncherSettings.default_settings
            ):
                try:
                    self.add_option(option, per_game=True)
                except Exception:
                    print("Error adding quick setting")
                    traceback.print_exc()

        self.layout.add(
            fsui.Label(self, gettext("Game Monitor")),
            margin=10,
            margin_bottom=0,
        )
        self.monitor_choice = MonitorChoice(self, per_game=True)
        self.monitor_button = self.monitor_choice
        self.layout.add(self.monitor_choice, fill=True, margin=10)

        fullscreen_layout = fsui.HorizontalLayout()
        self.fullscreen_checkbox = fsui.CheckBox(
            self, gettext("Default fullscreen")
        )
        self.fullscreen_checkbox.set_tooltip(
            gettext("Changes the global fullscreen default for all games")
        )
        self.fullscreen_checkbox.on_changed = self.on_fullscreen_changed
        fullscreen_layout.add(self.fullscreen_checkbox)
        self.fullscreen_warning = OverrideWarning(self, Option.FULLSCREEN)
        fullscreen_layout.add(self.fullscreen_warning, margin_left=10)
        fullscreen_layout.add_spacer(0, expand=True)
        self.layout.add(fullscreen_layout, fill=True, margin=10)
        self.video_sync_group = OptionUI.create_group(
            self,
            Option.VIDEO_SYNC,
            gettext("Video Sync"),
            help_button=False,
            thin=True,
            per_game=True,
        )
        self.layout.add(self.video_sync_group, fill=True, margin=10)
        self.screen_info_label = ScreenInfoLabel(self)
        # fsui does not relayout when the initially empty label gains text.
        self.screen_info_label.set_min_height(
            self.screen_info_label.measure_text(" ")[1]
        )
        self.layout.add(self.screen_info_label, fill=True, margin=10)

        ConfigBehavior(self, [Option.PLATFORM, Option.MONITOR])
        SettingsBehavior(self, [Option.G_SYNC, Option.FULLSCREEN])

    def add_option(
        self, option, platforms=None, enable=None, text="", per_game=False
    ):
        panel = fsui.Panel(self)
        panel.layout = fsui.VerticalLayout()
        panel.layout.add(
            OptionUI.create_group(
                panel,
                option,
                text,
                thin=True,
                help_button=False,
                per_game=per_game,
            ),
            fill=True,
        )
        self.layout.add(panel, fill=True, margin=10)
        if platforms:
            PlatformShowBehavior(panel, platforms)
        elif enable:
            PlatformEnableBehavior(panel, enable)

    def on_platform_config(self, value):
        self.layout.update()
        self.on_g_sync_setting(LauncherSettings.get(Option.G_SYNC))
        self.update_fullscreen_enabled()

    def on_g_sync_setting(self, value):
        self.video_sync_group.value_control.enable(
            value != "1"
            and LauncherConfig.game_override_identity() is not None
        )

    def on_monitor_config(self, value):
        self.on_g_sync_setting(LauncherSettings.get(Option.G_SYNC))
        self.update_fullscreen_enabled()

    def update_fullscreen_enabled(self):
        self.fullscreen_checkbox.enable(
            LauncherConfig.game_override_identity() is not None
        )

    def on_fullscreen_setting(self, value):
        with self.fullscreen_checkbox.changed.inhibit:
            self.fullscreen_checkbox.check(value == "1")
        self.update_fullscreen_enabled()

    def on_fullscreen_changed(self):
        if LauncherConfig.game_override_identity() is None:
            return
        LauncherSettings.set(
            Option.FULLSCREEN,
            "1" if self.fullscreen_checkbox.is_checked() else "0",
        )

    def on_settings_button(self):
        SettingsDialog.open(self.window)
