import traceback

import fsui
from fsgs.option import Option
from launcher.i18n import gettext
from launcher.launcher_settings import LauncherSettings
from launcher.option import options
from launcher.settings.monitorbutton import MonitorChoice
from launcher.settings.option_ui import OptionUI
from launcher.settings.override_warning import OverrideWarning
from launcher.settings.settings_dialog import SettingsDialog
from launcher.settings.videosynccheckbox import VideoSyncCheckBox
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

        self.add_option(Option.SCALE, text=None, enable=AMIGA_PLATFORMS)
        self.add_option(Option.STRETCH, text=None, enable=AMIGA_PLATFORMS)
        self.add_option(Option.BEZEL, text=None, enable=AMIGA_PLATFORMS)
        self.add_option(Option.ZOOM, text=None, platforms=AMIGA_PLATFORMS)

        quick_settings = LauncherSettings.get(Option.QUICK_SETTINGS_OPTIONS)
        for option in quick_settings.split(","):
            option = option.strip().lower()
            if "[" in option:
                # For future use of e.g.:
                # option1[platform1,platform2],option2[platform,...]
                option = option.split("[", 1)[0]
            if option in options:
                try:
                    self.add_option(option)
                except Exception:
                    print("Error adding quick setting")
                    traceback.print_exc()

        self.layout.add(fsui.Label(self, gettext("Game Monitor")), margin=10, margin_bottom=0)
        self.monitor_choice = MonitorChoice(self)
        self.monitor_button = self.monitor_choice
        self.layout.add(self.monitor_choice, fill=True, margin=10)

        fullscreen_layout = fsui.HorizontalLayout()
        self.fullscreen_checkbox = fsui.CheckBox(self, gettext("Fullscreen"))
        self.fullscreen_checkbox.on_changed = self.on_fullscreen_changed
        fullscreen_layout.add(self.fullscreen_checkbox)
        self.fullscreen_warning = OverrideWarning(self, Option.FULLSCREEN)
        fullscreen_layout.add(self.fullscreen_warning, margin_left=10)
        self.video_sync_checkbox = VideoSyncCheckBox(self)
        fullscreen_layout.add(self.video_sync_checkbox, margin_left=20)
        fullscreen_layout.add_spacer(0, expand=True)
        self.layout.add(fullscreen_layout, fill=True, margin=10)
        self.screen_info_label = ScreenInfoLabel(self)
        # fsui does not relayout when the initially empty label gains text.
        self.screen_info_label.set_min_height(
            self.screen_info_label.measure_text(" ")[1]
        )
        self.layout.add(self.screen_info_label, fill=True, margin=10)

        ConfigBehavior(self, [Option.PLATFORM])
        SettingsBehavior(self, [Option.G_SYNC, Option.FULLSCREEN])

    def add_option(self, option, platforms=None, enable=None, text=""):
        panel = fsui.Panel(self)
        panel.layout = fsui.VerticalLayout()
        panel.layout.add(
            OptionUI.create_group(
                panel, option, text, thin=True, help_button=False
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

    def on_g_sync_setting(self, value):
        self.video_sync_checkbox.enable(value != "1")

    def on_fullscreen_setting(self, value):
        with self.fullscreen_checkbox.changed.inhibit:
            self.fullscreen_checkbox.check(value == "1")

    def on_fullscreen_changed(self):
        LauncherSettings.set(
            Option.FULLSCREEN,
            "1" if self.fullscreen_checkbox.is_checked() else "0",
        )

    def on_settings_button(self):
        SettingsDialog.open(self.window)
