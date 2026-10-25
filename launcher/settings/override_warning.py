import fsui
from launcher.i18n import gettext
from launcher.ui.behaviors.configbehavior import ConfigBehavior


class OverrideWarning(fsui.ImageView):
    def __init__(self, parent, name):
        fsui.ImageView.__init__(
            self, parent, fsui.Image("launcher:res/16x16/warning_2.png")
        )
        setattr(self, f"on_{name}_config", self.on_config)
        ConfigBehavior(self, [name])
        text = gettext(
            f"Option {name} is overridden by current configuration"
        )
        self.set_tool_tip(text)

    def on_config(self, value):
        self.show_or_hide(bool(value))
