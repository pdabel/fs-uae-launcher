import traceback

import fsui
from fsgs.option import Option
from launcher.i18n import gettext
from launcher.option import options
from launcher.settings.fullscreenmodebutton import FullscreenModeButton
from launcher.settings.monitorbutton import MonitorButton
from launcher.settings.option_ui import OptionUI
from launcher.settings.settings_dialog import SettingsDialog
from launcher.settings.videosynccheckbox import VideoSyncCheckBox
from launcher.ui.IconButton import IconButton
from launcher.ui.behaviors.configbehavior import ConfigBehavior
from launcher.ui.behaviors.platformbehavior import (
    PlatformShowBehavior,
    AMIGA_PLATFORMS,
    PlatformEnableBehavior,
)
from launcher.ui.behaviors.settingsbehavior import SettingsBehavior


class QuickSettingsPanel(fsui.Panel):
    def __init__(self, parent, fsgc):
        self.fsgc = fsgc
        super().__init__(parent)
        self.layout = fsui.VerticalLayout()

        hori_layout = fsui.HorizontalLayout()
        self.layout.add(hori_layout, fill=True)
        heading_label = fsui.HeadingLabel(self, gettext("Settings"))
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

        quick_settings = fsgc.settings[Option.QUICK_SETTINGS_OPTIONS]
        for option in quick_settings.split(","):
            option = option.strip().lower()
            if "[" in option:
                # For future use of e.g.:
                # option1[platform1,platform2],option2[platform,...]
                option, platforms = option.split("[", 1)
            else:
                platforms = []
            if option in options:
                try:
                    self.add_option(option)
                except Exception:
                    print("Error adding quick setting")
                    traceback.print_exc()

        self.layout.add_spacer(expand=True)

        hori_layout = fsui.HorizontalLayout()
        hori_layout.add_spacer(expand=True)
        self.video_sync_checkbox = VideoSyncCheckBox(self)
        hori_layout.add(self.video_sync_checkbox, margin_right=10)
        self.layout.add(hori_layout, fill=True)
        self.monitor_button = MonitorButton(self)
        hori_layout.add(self.monitor_button, fill=True, margin_right=10)
        if False:
            self.fullscreen_mode_button = FullscreenModeButton(self)
            hori_layout.add(
                self.fullscreen_mode_button, fill=True, margin_right=10
            )
        self.layout.add_spacer(10)

        ConfigBehavior(self, [Option.PLATFORM])
        SettingsBehavior(self, [Option.G_SYNC])

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

    def on_settings_button(self):
        SettingsDialog.open(self.window)

    def get_min_height(self):
        # Because we add a lot of controls, force min size to 0 to avoid
        # this control reporting too large min height at startup.
        return 0
