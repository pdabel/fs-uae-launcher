import fsui
from qtpy.QtCore import QRect, Qt, QTimer, QSignalBlocker
from qtpy.QtGui import QColor, QFontMetrics, QPainter, QPen
from qtpy.QtWidgets import QWidget
from fsui.qt import init_qt, modern_theme
from fsgs.displays import (
    display_id,
    display_label,
    fsuae_monitor,
    matching_display_index,
    screen_index,
)
from launcher.i18n import gettext
from launcher.launcher_config import LauncherConfig
from launcher.launcher_settings import LauncherSettings
from launcher.ui.behaviors.configbehavior import ConfigBehavior
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
        theme = modern_theme.palette()
        painter.fillRect(self.rect(), QColor(theme.dark))
        painter.setPen(QPen(QColor(theme.light), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        font = painter.font()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        painter.setPen(QColor(theme.brand))
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
                rect, QColor(theme.pressed if selected else theme.raised)
            )
            painter.setPen(
                QPen(
                    QColor(theme.accent if selected else theme.border_hover),
                    3 if selected else 1,
                )
            )
            painter.drawRect(rect)
            painter.setPen(QColor(theme.brand))
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
    def __init__(self, parent, setting_key="monitor", per_game=False):
        super().__init__(parent)
        self.setMinimumContentsLength(12)
        self.setSizeAdjustPolicy(
            self.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.setting_key = setting_key
        self.per_game = per_game
        self.values = []
        self.monitor_highlight = None
        self.application = init_qt()
        self.highlighted.connect(self.on_highlighted)
        self.activated.connect(self.on_monitor_activated)
        tooltip = (
            "Display preferred for the launcher window"
            if setting_key == "launcher_monitor"
            else "Monitor used when starting a game"
        )
        self.set_tooltip(gettext(tooltip))
        self.application.screenAdded.connect(self.on_screen_added)
        self.application.screenRemoved.connect(self.refresh)
        self.application.primaryScreenChanged.connect(self.refresh)
        for screen in self.application.screens():
            self.watch_screen(screen)
        if per_game:
            ConfigBehavior(self, ["monitor", "__game_override_context"])
            SettingsBehavior(self, ["monitor"])
        else:
            SettingsBehavior(self, [setting_key])

    def watch_screen(self, screen):
        screen.geometryChanged.connect(self.refresh)

    def on_screen_added(self, screen):
        self.watch_screen(screen)
        self.refresh()

    def on_monitor_setting(self, value):
        self.refresh()

    def on_monitor_config(self, value):
        self.refresh()

    def on___game_override_context_config(self, value):
        self.refresh()

    def on_settings(self, key, value):
        if key == self.setting_key:
            self.refresh()

    def refresh(self, *arguments):
        if self.monitor_highlight is not None:
            self.monitor_highlight.timer.stop()
            self.monitor_highlight.hide()
        screens = self.application.screens()
        if self.per_game:
            overrides = LauncherConfig.get_game_overrides()
            has_override = "monitor" in overrides
            current = (
                overrides.get("monitor", "")
                if has_override
                else LauncherConfig.get_game_base_value("monitor")
            )
            global_monitor = LauncherSettings.get("monitor")
            global_index = screen_index(
                screens, global_monitor, self.application.primaryScreen()
            )
            if global_index is None:
                default_name = gettext("Primary display")
            else:
                default_name = display_label(screens[global_index])
            entries = [
                (
                    None,
                    gettext("Default ({display})").format(
                        display=default_name
                    ),
                ),
                ("", gettext("Use FS-UAE default")),
            ]
            entries.extend(
                (display_id(screen), display_label(screen))
                for screen in screens
            )
            if current.startswith("display:"):
                selected_index = matching_display_index(screens, current)
            else:
                selected_index = screen_index(
                    screens, current, self.application.primaryScreen()
                )
            if has_override and current:
                if selected_index is not None:
                    value, label = entries[selected_index + 2]
                    entries[selected_index + 2] = (
                        value,
                        gettext("{display} (Game override)").format(
                            display=label
                        ),
                    )
            if not has_override and not current:
                selected = 0
            elif has_override and current == "":
                selected = 1
            else:
                selected = (
                    selected_index + 2 if selected_index is not None else None
                )
        else:
            current = LauncherSettings.get(self.setting_key)
            entries = [("", gettext("Primary display (*)"))]
            entries.extend(
                (display_id(screen), display_label(screen))
                for screen in screens
            )
            if current == "primary" or not current:
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
                if selected is None and current.startswith("display:"):
                    matching = matching_display_index(screens, current)
                    if matching is not None:
                        selected = matching + 1
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
                else gettext(
                    "{display} (saved display unavailable; using primary)"
                ).format(display=current)
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
        if self.per_game:
            self.set_enabled(LauncherConfig.game_overrides_available())

    def on_changed(self):
        index = self.get_index()
        if 0 <= index < len(self.values):
            value = self.values[index]
            if self.per_game:
                if value is None:
                    LauncherConfig.clear_game_override("monitor")
                else:
                    LauncherConfig.set_game_override("monitor", value)
                self.show_monitor_highlight(self.get_index(), 1800)
            else:
                if (
                    self.setting_key == "monitor"
                    and fsuae_monitor(
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
                LauncherSettings.set(self.setting_key, value)
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
            screens,
            (
                LauncherSettings.get("monitor")
                if self.per_game and self.values[index] is None
                else self.values[index]
            ),
            self.application.primaryScreen(),
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
