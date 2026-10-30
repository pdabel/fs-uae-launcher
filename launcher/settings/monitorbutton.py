import fsui
from qtpy.QtCore import QRect, Qt, QTimer, QSignalBlocker
from qtpy.QtGui import QColor, QFontMetrics, QPainter, QPen
from qtpy.QtWidgets import QWidget
from fsui.qt import init_qt
from fsgs.displays import (
    display_id,
    display_label,
    fsuae_monitor,
    screen_index,
)
from launcher.i18n import gettext
from launcher.launcher_settings import LauncherSettings
from launcher.ui.behaviors.settingsbehavior import SettingsBehavior


class MonitorHighlight(QWidget):
    def __init__(self, parent):
        super().__init__(parent, Qt.Widget)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.text = ""
        self.screens = []
        self.selected = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)

    def show_monitor(self, screen, text, duration=0):
        self.timer.stop()
        self.hide()
        self.text = text
        self.screens = init_qt().screens()
        self.selected = screen
        parent = self.parentWidget()
        width = min(360, max(1, parent.width() - 24))
        height = min(160, max(1, parent.height() - 24))
        self.setGeometry(
            max(0, parent.width() - width - 12),
            max(0, parent.height() - height - 12),
            width,
            height,
        )
        self.show()
        self.raise_()
        self.update()
        if duration:
            self.timer.start(duration)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#101218"))
        painter.setPen(QPen(QColor("#454c62"), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        font = painter.font()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(
            QRect(10, 4, max(1, self.width() - 20), metrics.height() + 8),
            Qt.AlignLeft | Qt.AlignVCenter,
            metrics.elidedText(
                self.text, Qt.ElideRight, max(1, self.width() - 20)
            ),
        )
        for screen, rect in self.monitor_rects():
            selected = screen is self.selected
            painter.fillRect(
                rect, QColor("#253e54") if selected else QColor("#292d3e")
            )
            painter.setPen(
                QPen(
                    QColor("#46b7ee") if selected else QColor("#7f879c"),
                    3 if selected else 1,
                )
            )
            painter.drawRect(rect)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(
                rect.adjusted(4, 0, -4, 0),
                Qt.AlignCenter,
                metrics.elidedText(
                    screen.name(), Qt.ElideRight, max(1, rect.width() - 8)
                ),
            )

    def monitor_rects(self):
        if not self.screens:
            return []
        bounds = QRect(self.screens[0].geometry())
        for screen in self.screens[1:]:
            bounds = bounds.united(screen.geometry())
        area = self.rect().adjusted(12, 36, -12, -12)
        if area.width() <= 0 or area.height() <= 0 or bounds.isEmpty():
            return []
        scale = min(
            area.width() / bounds.width(), area.height() / bounds.height()
        )
        offset_x = area.x() + (area.width() - bounds.width() * scale) / 2
        offset_y = area.y() + (area.height() - bounds.height() * scale) / 2
        rectangles = []
        for screen in self.screens:
            geometry = screen.geometry()
            rect = QRect(
                round(offset_x + (geometry.x() - bounds.x()) * scale),
                round(offset_y + (geometry.y() - bounds.y()) * scale),
                max(1, round(geometry.width() * scale) - 4),
                max(1, round(geometry.height() * scale) - 4),
            )
            rectangles.append((screen, rect))
        return rectangles


class MonitorChoice(fsui.Choice):
    def __init__(self, parent):
        super().__init__(parent)
        self.setMinimumContentsLength(12)
        self.setSizeAdjustPolicy(
            self.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.values = []
        self.monitor_highlight = None
        self.application = init_qt()
        self.highlighted.connect(self.on_highlighted)
        self.activated.connect(self.on_monitor_activated)
        self.set_tooltip(gettext("Monitor used when starting a game"))
        self.application.screenAdded.connect(self.on_screen_added)
        self.application.screenRemoved.connect(self.refresh)
        self.application.primaryScreenChanged.connect(self.refresh)
        for screen in self.application.screens():
            self.watch_screen(screen)
        SettingsBehavior(self, ["monitor"])

    def watch_screen(self, screen):
        screen.geometryChanged.connect(self.refresh)

    def on_screen_added(self, screen):
        self.watch_screen(screen)
        self.refresh()

    def on_monitor_setting(self, value):
        self.refresh()

    def refresh(self, *arguments):
        if self.monitor_highlight is not None:
            self.monitor_highlight.timer.stop()
            self.monitor_highlight.hide()
        current = LauncherSettings.get("monitor")
        entries = [("", gettext("Primary display (*)"))]
        for screen in self.application.screens():
            entries.append((display_id(screen), display_label(screen)))
        if current == "primary":
            selected = 0
        else:
            selected = next(
                (
                    index
                    for index, entry in enumerate(entries)
                    if entry[0] == current
                ),
                None,
            )
        if selected is None:
            legacy = {
                "left": gettext("Left"),
                "middle-left": gettext("Middle Left"),
                "middle-right": gettext("Middle Right"),
                "right": gettext("Right"),
            }
            label = (
                gettext("{position} (legacy position)").format(
                    position=legacy[current]
                )
                if current in legacy
                else gettext("Saved display unavailable; using primary")
            )
            entries.append((current, label))
            selected = len(entries) - 1
        with self.changed.inhibit, QSignalBlocker(self):
            self.clear()
            self.values = [value for value, label in entries]
            for value, label in entries:
                self.add_item(label)
                self.setItemData(
                    self.count() - 1, label, fsui.qt.Qt.ToolTipRole
                )
            self.set_index(selected)

    def on_changed(self):
        index = self.get_index()
        if 0 <= index < len(self.values):
            value = self.values[index]
            if (
                fsuae_monitor(
                    self.application.screens(),
                    value,
                    self.application.primaryScreen(),
                )
                is None
            ):
                fsui.show_warning(
                    gettext(
                        "FS-UAE 3.x cannot uniquely select this monitor in fullscreen with the current display layout. Windowed placement will be requested, but the desktop may override it."
                    ),
                    gettext("Game Monitor"),
                    parent=self,
                )
            LauncherSettings.set("monitor", value)
            self.show_monitor_highlight(self.get_index(), 1800)

    def showPopup(self):
        super().showPopup()
        self.show_monitor_highlight(self.get_index())

    def hidePopup(self):
        super().hidePopup()
        if (
            self.monitor_highlight is not None
            and not self.monitor_highlight.timer.isActive()
        ):
            self.monitor_highlight.hide()

    def on_highlighted(self, index):
        self.show_monitor_highlight(index)

    def on_monitor_activated(self, index):
        self.show_monitor_highlight(index, 1800)

    def show_monitor_highlight(self, index, duration=0):
        if not 0 <= index < len(self.values):
            return
        screens = self.application.screens()
        target = screen_index(
            screens, self.values[index], self.application.primaryScreen()
        )
        if target is None:
            if self.monitor_highlight is not None:
                self.monitor_highlight.hide()
            return
        if self.monitor_highlight is None:
            self.monitor_highlight = MonitorHighlight(self.window())
        screen = screens[target]
        text = gettext("Display {number}: {name}").format(
            number=target + 1, name=screen.name()
        )
        self.monitor_highlight.show_monitor(screen, text, duration)


MonitorButton = MonitorChoice
