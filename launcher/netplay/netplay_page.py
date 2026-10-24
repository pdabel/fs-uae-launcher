import json

import fsui
from fsui.qt import Qt, QHBoxLayout, QScrollArea, QSplitter, QTimer
from launcher.launcher_settings import LauncherSettings
from launcher.netplay.netplay_panel import NetplayPanel
from launcher.netplay.server_details import ServerDetails


class NetplayPage(fsui.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self.widget().setObjectName("netplayPage")
        layout = QHBoxLayout(self.widget())
        layout.setContentsMargins(0, 0, 0, 0)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(16)
        layout.addWidget(self.splitter)
        self.panel = NetplayPanel(self, header=False, columns=True)
        self.channel_area = QScrollArea()
        self.channel_area.setWidgetResizable(True)
        self.channel_area.setMinimumWidth(
            self.panel.channel_panel.get_min_width() + 2
        )
        self.channel_area.setWidget(self.panel.channel_panel.widget())
        self.splitter.addWidget(self.channel_area)
        self.chat_area = QScrollArea()
        self.chat_area.setWidgetResizable(True)
        self.chat_area.setMinimumWidth(220)
        self.chat_area.setWidget(self.panel.widget())
        self.splitter.addWidget(self.chat_area)
        self.server_details = ServerDetails()
        self.server_details.layout().insertWidget(
            self.server_details.layout().count() - 1,
            self.panel.game_panel.widget(),
        )
        self.details_area = QScrollArea()
        self.details_area.setWidgetResizable(True)
        self.details_area.setMinimumWidth(240)
        self.details_area.setWidget(self.server_details)
        self.splitter.addWidget(self.details_area)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 1)
        self._column_sizes = [25, 40, 35]
        try:
            sizes = json.loads(LauncherSettings.get("netplay_column_sizes"))
            if (isinstance(sizes, list) and len(sizes) == 3
                    and all(type(size) is int and 0 < size <= 1000000 for size in sizes)):
                self._column_sizes = sizes
        except (TypeError, ValueError):
            pass
        self.splitter.setSizes(self._column_sizes)
        self.splitter.splitterMoved.connect(self._save_column_sizes)
        QTimer.singleShot(0, self._restore_column_sizes)
        self.panel.create_server_view = self.server_details.present
        self.panel.on_action_layout_changed = self._update_chat_size
        self._update_chat_size()
        self.panel.show()

    def _update_chat_size(self):
        self.panel.widget().setMinimumSize(
            self.panel.get_min_width(), self.panel.get_min_height()
        )
        for panel in (self.panel.channel_panel, self.panel.game_panel):
            panel.widget().setMinimumSize(panel.get_min_width(), panel.get_min_height())

    def _restore_column_sizes(self):
        available = self.splitter.width() - 2 * self.splitter.handleWidth()
        total = sum(self._column_sizes)
        self.splitter.setSizes([
            round(available * size / total) for size in self._column_sizes
        ])

    def _save_column_sizes(self, position, index):
        sizes = self.splitter.sizes()
        if all(size > 0 for size in sizes):
            self._column_sizes = sizes
            LauncherSettings.set("netplay_column_sizes", json.dumps(sizes))

    def on_show(self):
        self.panel.on_show()

    def shutdown(self):
        self.panel.on_destroy()
        self.server_details.close()