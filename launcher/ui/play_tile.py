"""One-click Play card shown above the library in the Modern Dark dashboard.

Non-technical users see the selected game's name and a single large Play
button; the configuration editor is tucked behind an "Edit configuration"
toggle whose state is remembered in launcher settings.
"""

from fsui.qt import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, Qt,
)
from launcher.i18n import gettext
from launcher.launcher_settings import LauncherSettings
from launcher.ui.behaviors.configbehavior import ConfigBehavior
from launcher.ui.navigation_icons import navigation_icon

EDITOR_SETTING = "launcher_show_editor"


class PlayTile(QFrame):
    def __init__(self, owner, parent=None):
        super().__init__(parent)
        self.owner = owner
        self._name = ""
        self.setObjectName("playTile")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(16)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.eyebrow = QLabel(gettext("READY TO PLAY"))
        self.eyebrow.setObjectName("eyebrow")
        text.addWidget(self.eyebrow)
        self.title = QLabel()
        self.title.setObjectName("playTitle")
        self.title.setTextFormat(Qt.PlainText)
        self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        text.addWidget(self.title)
        self.subtitle = QLabel()
        self.subtitle.setObjectName("playSubtitle")
        self.subtitle.setTextFormat(Qt.PlainText)
        text.addWidget(self.subtitle)
        layout.addLayout(text, 1)
        self.play_button = QPushButton(
            navigation_icon("fa5s.play"), gettext("Play")
        )
        self.play_button.setObjectName("playButton")
        self.play_button.setMinimumSize(132, 56)
        self.play_button.setCursor(Qt.PointingHandCursor)
        self.play_button.setToolTip(gettext("Start the selected game or configuration"))
        self.play_button.clicked.connect(self.on_play)
        layout.addWidget(self.play_button)
        self.edit_button = QPushButton(
            navigation_icon("fa5s.sliders-h"), gettext("Edit configuration")
        )
        self.edit_button.setObjectName("editButton")
        self.edit_button.setCheckable(True)
        self.edit_button.setMinimumHeight(40)
        self.edit_button.setToolTip(gettext(
            "Show or hide the detailed configuration pages for this game"
        ))
        layout.addWidget(self.edit_button)
        LauncherSettings.add_listener(self)
        self.on_setting("config_name", LauncherSettings.get("config_name"))
        self._update_subtitle()
        ConfigBehavior(self, ["__running"])

    def shutdown(self):
        LauncherSettings.remove_listener(self)

    @staticmethod
    def editor_visible_setting():
        return LauncherSettings.get(EDITOR_SETTING) == "1"

    @staticmethod
    def remember_editor_visible(visible):
        LauncherSettings.set(EDITOR_SETTING, "1" if visible else "0")

    def on_play(self):
        from launcher.launcherapp import LauncherApp

        LauncherApp.start_game()

    def on___running_config(self, value):
        self.set_running(value == "1")

    def set_running(self, running):
        self.play_button.setEnabled(not running)
        self.play_button.setText(gettext("Running") if running else gettext("Play"))

    def on_setting(self, key, value):
        if key == "config_name":
            self._name = value.strip()
            self._update_title()
        elif key in ("parent_uuid", "config_path"):
            self._update_subtitle()

    def _update_subtitle(self):
        if LauncherSettings.get("parent_uuid"):
            self.subtitle.setText(gettext("Game from the online database"))
        elif LauncherSettings.get("config_path"):
            self.subtitle.setText(gettext("Your saved configuration"))
        else:
            self.subtitle.setText(gettext("Pick a game from the library below"))

    def _update_title(self):
        name = self._name or gettext("Amiga 500 (default setup)")
        metrics = self.title.fontMetrics()
        width = max(120, self.title.width() - 8)
        self.title.setText(metrics.elidedText(name, Qt.ElideRight, width))
        self.title.setToolTip(name)
        self.play_button.setAccessibleName(
            gettext("Play {name}").format(name=name)
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_title()

    def restyle_icons(self):
        self.play_button.setIcon(navigation_icon("fa5s.play"))
        self.edit_button.setIcon(navigation_icon("fa5s.sliders-h"))


__all__ = ["PlayTile", "EDITOR_SETTING"]
