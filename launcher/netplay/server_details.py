import fsui
import qtawesome as qta

from fsui.qt import (
    Qt, QFrame, QLabel, QPushButton, QTimer, QVBoxLayout,
)
from launcher.i18n import gettext


class ServerDetails(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.server = None
        self.setObjectName("serverDetails")
        self.setMinimumWidth(240)
        self.setStyleSheet("""
            QFrame#serverDetails { background: #212431; }
            QLabel[detailLabel="true"] { color: #a2abc0; font-size: 12px; }
            QLabel#serverStatus { color: #69d6ae; font-weight: 600; }
        """)
        if fsui.theme_variant != "modern":
            self.setStyleSheet("""
                QFrame#serverDetails { background: palette(window); }
                QLabel[detailLabel="true"] { font-size: 12px; }
                QLabel#serverStatus { font-weight: 600; }
            """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        heading = QLabel(gettext("Netplay server"))
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        self.status = QLabel(gettext("Not hosting"))
        self.status.setObjectName("serverStatus")
        layout.addWidget(self.status)
        layout.addSpacing(12)
        self.fields = {}
        for name, title in (
            ("game_id", "Game ID"), ("channel", "Channel"),
            ("port", "Port"), ("players", "Players"),
        ):
            label = QLabel(gettext(title))
            label.setProperty("detailLabel", True)
            layout.addWidget(label)
            value = QLabel("-")
            value.setWordWrap(True)
            value.setTextFormat(Qt.PlainText)
            value.setTextInteractionFlags(
                Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
            )
            value.setMinimumWidth(0)
            layout.addWidget(value)
            layout.addSpacing(10)
            self.fields[name] = value
        layout.addStretch(1)
        self.stop_button = QPushButton(
            qta.icon("fa5s.stop", color="#fa7979"), gettext("Stop server")
        )
        self.stop_button.setToolTip(gettext("Stop the hosted netplay server"))
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_server)
        layout.addWidget(self.stop_button)
        self.monitor = QTimer(self)
        self.monitor.setInterval(1000)
        self.monitor.timeout.connect(self._check_server)

    def present(self, parent, server, game_id, port, channel):
        self.stop_server()
        self.server = server
        self.fields["game_id"].setText(game_id)
        self.fields["channel"].setText(channel)
        self.fields["port"].setText(str(port))
        self.fields["players"].setText(str(server.players))
        self.status.setText(gettext("Hosting"))
        self.stop_button.setEnabled(True)
        self.monitor.start()
        return self

    def stop_server(self):
        if self.server is not None:
            self.server.stop()
            self.server = None
            self.status.setText(gettext("Stopped"))
        self.stop_button.setEnabled(False)
        self.monitor.stop()

    def _check_server(self):
        if self.server is not None and self.server.process is not None:
            if self.server.process.poll() is not None:
                self.stop_server()

    def close(self):
        self.stop_server()
        return True