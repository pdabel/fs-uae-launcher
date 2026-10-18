import fsui
from fsui import ImageButton, Image


class IconButton(ImageButton):

    BUTTON_WIDTH = 40

    def __init__(self, parent, name):
        image = Image("launcher:res/" + name)
        ImageButton.__init__(self, parent, image)
        self.set_min_width(self.BUTTON_WIDTH)
        self._apply_modern_icon(name)

    def set_icon_name(self, name):
        image = Image("launcher:res/" + name)
        self.set_image(image)
        self._apply_modern_icon(name)

    def _apply_modern_icon(self, name):
        if fsui.theme_variant == "modern" and name in (
            "16x16/information.png", "info.png"
        ):
            import qtawesome as qta
            from fsui.qt import QSize

            self.widget().setIcon(qta.icon("fa5s.info-circle", color="#9bcce2"))
            self.widget().setIconSize(QSize(18, 18))
