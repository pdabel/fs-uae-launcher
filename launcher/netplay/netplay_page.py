import fsui
from fsui.qt import Qt, QHBoxLayout, QScrollArea, QSplitter
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
        self.panel = NetplayPanel(self, header=False)
        self.chat_area = QScrollArea()
        self.chat_area.setWidgetResizable(True)
        self.chat_area.setMinimumWidth(350)
        self.chat_area.setWidget(self.panel.widget())
        self.splitter.addWidget(self.chat_area)
        self.server_details = ServerDetails()
        self.splitter.addWidget(self.server_details)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([1100, 280])
        self.panel.create_server_view = self.server_details.present
        self.panel.on_action_layout_changed = self._update_chat_size
        self._update_chat_size()
        self.panel.show()

    def _update_chat_size(self):
        self.panel.widget().setMinimumSize(
            self.panel.get_min_width(), self.panel.get_min_height()
        )

    def on_show(self):
        self.panel.on_show()

    def shutdown(self):
        self.panel.on_destroy()
        self.server_details.close()