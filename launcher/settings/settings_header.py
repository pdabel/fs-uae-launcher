import fsui
from fsbc.util import unused


class SettingsHeader(fsui.Group):

    ICON_LEFT = 0
    ICON_RIGHT = 1

    def __init__(
        self, parent, icon, title, subtitle="", icon_position=ICON_RIGHT
    ):
        unused(subtitle)
        fsui.Group.__init__(self, parent)
        self.layout = fsui.HorizontalLayout()

        self.image_view = None
        self.title_label = fsui.HeadingLabel(self, title)
        font = self.title_label.font()
        font.setPixelSize(25)
        font.setBold(True)
        self.title_label.setFont(font)
        self.layout.add(self.title_label, expand=True, fill=True)
