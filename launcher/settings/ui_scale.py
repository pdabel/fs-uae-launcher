import fsui
from fsui.qt import (
    QFontDatabase, QHBoxLayout, QLabel, QSignalBlocker, QSlider, QVBoxLayout,
    Qt,
)
from launcher.i18n import gettext
from launcher.launcher_settings import LauncherSettings
from launcher.option import Option


def default_point_size():
    return QFontDatabase.systemFont(QFontDatabase.GeneralFont).pointSize()


class UIScaleSlider(fsui.Panel):
    """A Smaller / Default / Larger slider that stores launcher_font_size.

    Dragging previews live through the LauncherSettings listener in the
    settings page; the stored value stays a point size so existing
    preferences and the --launcher-font-size handling are unchanged.
    """

    def __init__(self, parent):
        super().__init__(parent)
        option = Option.get(Option.LAUNCHER_FONT_SIZE)
        self.minimum = option["min"]
        self.maximum = option["max"]
        self.default = max(self.minimum, min(self.maximum, default_point_size()))
        container = self.widget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        header = QHBoxLayout()
        title = QLabel(gettext("Interface size"))
        header.addWidget(title)
        header.addStretch(1)
        self.caption = QLabel()
        self.caption.setObjectName("uiScaleCaption")
        header.addWidget(self.caption)
        layout.addLayout(header)
        row = QHBoxLayout()
        row.setSpacing(10)
        smaller = QLabel(gettext("Smaller"))
        row.addWidget(smaller)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(self.minimum, self.maximum)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(2)
        self.slider.setTickPosition(QSlider.TicksBelow)
        self.slider.setTickInterval(1)
        self.slider.setAccessibleName(gettext("Interface size"))
        self.slider.setToolTip(gettext(
            "Make text and controls smaller or larger. "
            "The middle notch is your system's default size."
        ))
        row.addWidget(self.slider, 1)
        larger = QLabel(gettext("Larger"))
        row.addWidget(larger)
        layout.addLayout(row)
        self.reset_button = fsui.Button(self, gettext("Use Default Size"))
        self.reset_button.activated.connect(self.on_reset)
        reset_row = QHBoxLayout()
        reset_row.addStretch(1)
        reset_row.addWidget(self.reset_button.widget())
        layout.addLayout(reset_row)
        self.set_min_height(layout.sizeHint().height())

        self.slider.valueChanged.connect(self.on_value_changed)
        self.slider.sliderReleased.connect(self.commit)
        self.on_setting(Option.LAUNCHER_FONT_SIZE, LauncherSettings.get(Option.LAUNCHER_FONT_SIZE))
        LauncherSettings.add_listener(self)

    def on_destroy(self):
        LauncherSettings.remove_listener(self)

    def value(self):
        return self.slider.value()

    def stored_value(self):
        value = self.slider.value()
        return "" if value == self.default else str(value)

    def describe(self, value):
        if value < self.default:
            label = gettext("Smaller")
        elif value > self.default:
            label = gettext("Larger")
        else:
            label = gettext("Default")
        return f"{label} ({value} pt)"

    def on_value_changed(self, value):
        self.caption.setText(self.describe(value))
        self.reset_button.set_enabled(value != self.default)
        if not self.slider.isSliderDown():
            self.commit()

    def commit(self):
        LauncherSettings.set(Option.LAUNCHER_FONT_SIZE, self.stored_value())

    def on_reset(self):
        self.slider.setValue(self.default)

    def on_setting(self, key, value):
        if key != Option.LAUNCHER_FONT_SIZE:
            return
        try:
            point_size = int(value)
        except (TypeError, ValueError):
            point_size = self.default
        point_size = max(self.minimum, min(self.maximum, point_size))
        with QSignalBlocker(self.slider):
            self.slider.setValue(point_size)
        self.caption.setText(self.describe(point_size))
        self.reset_button.set_enabled(point_size != self.default)
