import fsui
from fsui.qt import (
    QHBoxLayout, QLabel, QSignalBlocker, QSlider, QVBoxLayout,
    Qt,
)
from fsui.qt.qt import (
    applied_launcher_theme, theme_applied, theme_default_point_size,
)
from launcher.i18n import gettext
from launcher.launcher_settings import LauncherSettings
from launcher.option import Option


def default_point_size():
    """The point size of the selected theme without a size override."""
    theme = applied_launcher_theme()
    if theme is None:
        theme = LauncherSettings.get(Option.LAUNCHER_THEME)
    return theme_default_point_size(theme)


class UIScaleSlider(fsui.Panel):
    """Synchronized slider and numeric control for launcher_font_size.

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
        self.title = QLabel(gettext("Interface Font Size"))
        header.addWidget(self.title)
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
        self.slider.setAccessibleName(gettext("Interface Font Size"))
        self.slider.setToolTip(gettext(
            "Adjust the interface font size in points. "
            "Use Default Size restores the selected theme's default."
        ))
        row.addWidget(self.slider, 1)
        larger = QLabel(gettext("Larger"))
        row.addWidget(larger)
        self.spin_control = fsui.SpinCtrl(
            self, self.minimum, self.maximum, self.default
        )
        self.spinbox = self.spin_control.widget()
        self.spinbox.setSuffix(gettext(" pt"))
        self.spinbox.setKeyboardTracking(False)
        self.spinbox.setAccessibleName(gettext("Interface Font Size"))
        self.spinbox.setToolTip(self.slider.toolTip())
        self.spin_control.on_changed = self.on_spin_changed
        row.addWidget(self.spinbox)
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
        theme_applied.connect(self.refresh_default)

    def on_destroy(self):
        theme_applied.disconnect(self.refresh_default)
        LauncherSettings.remove_listener(self)

    def refresh_default(self):
        """Follow the selected theme's own default font size."""
        default = max(self.minimum, min(self.maximum, default_point_size()))
        if default != self.default:
            self.default = default
            self.on_setting(
                Option.LAUNCHER_FONT_SIZE,
                LauncherSettings.get(Option.LAUNCHER_FONT_SIZE),
            )

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
        with QSignalBlocker(self.spinbox):
            self.spinbox.setValue(value)
        self.caption.setText(self.describe(value))
        self.reset_button.set_enabled(
            value != self.default or self.has_override()
        )
        if not self.slider.isSliderDown():
            self.commit()

    def on_spin_changed(self):
        self.slider.setValue(self.spinbox.value())

    def has_override(self):
        return bool(str(LauncherSettings.get(Option.LAUNCHER_FONT_SIZE)).strip())

    def commit(self):
        LauncherSettings.set(Option.LAUNCHER_FONT_SIZE, self.stored_value())

    def on_reset(self):
        self.slider.setValue(self.default)
        LauncherSettings.set(Option.LAUNCHER_FONT_SIZE, "")

    def on_setting(self, key, value):
        if key != Option.LAUNCHER_FONT_SIZE:
            return
        try:
            point_size = int(value)
        except (TypeError, ValueError):
            point_size = self.default
        point_size = max(self.minimum, min(self.maximum, point_size))
        with QSignalBlocker(self.slider), QSignalBlocker(self.spinbox):
            self.slider.setValue(point_size)
            self.spinbox.setValue(point_size)
        self.caption.setText(self.describe(point_size))
        self.reset_button.set_enabled(
            point_size != self.default or bool(str(value or "").strip())
        )
