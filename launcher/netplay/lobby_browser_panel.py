"""The Net Play tab's lobby browser: servers, the games on them, and an
activity log. See "UX" in docs/netplay-rooms-design.md.

Names, titles and server names come from other users, so every one of
them is shown as plain text.
"""

import time

import fsui
from fsui.qt import modern_theme
from fsui.qt.qt import theme_applied
from fsui.qt import (
    Qt,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTimer,
    QVBoxLayout,
)
from qtpy.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QPlainTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
)
from launcher.i18n import gettext
from launcher.netplay.lobby_browser import (
    CONNECTING,
    NO_LISTING,
    ONLINE,
    UNREACHABLE,
)

# Status dots: filled when the server answers.
DOT_ONLINE = "●"
DOT_OFFLINE = "○"


def plain_label(text="", object_name=None):
    label = QLabel(text)
    label.setTextFormat(Qt.PlainText)
    if object_name:
        label.setObjectName(object_name)
    return label


def server_status(server, now):
    """The status column for a server: its games, or why there are none."""
    if server.state == CONNECTING:
        return gettext("connecting…")
    if server.state == UNREACHABLE:
        retry_in = server.retry_in(now)
        if retry_in:
            return gettext("can't reach it, retrying in {0} s").format(
                retry_in
            )
        return gettext("can't reach it, retrying")
    if server.state == NO_LISTING:
        return server.error or gettext("doesn't list games")
    count = len(server.games)
    if count == 0:
        return gettext("no games")
    if count == 1:
        return gettext("1 game")
    return gettext("{0} games").format(count)


def game_players(game):
    if game.running:
        return gettext("running")
    return gettext("{0} of {1}").format(game.joined, game.players)


def game_action(game):
    """What the last column says when there's no Join button."""
    if game.running:
        return ""
    if game.full:
        return gettext("full")
    return ""


class LobbyBrowserPanel(QFrame):
    def __init__(self, netplay, open_settings=None, parent=None):
        super().__init__(parent)
        self.netplay = netplay
        self.open_settings = open_settings
        self.setObjectName("lobbyBrowser")
        self.restyle()
        theme_applied.connect(self.restyle)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        columns = QHBoxLayout()
        columns.setSpacing(20)
        layout.addLayout(columns, 1)

        servers_column = QVBoxLayout()
        columns.addLayout(servers_column, 2)
        servers_column.addWidget(
            plain_label(gettext("Servers"), "sectionTitle")
        )
        self.servers_tree = QTreeWidget()
        self.servers_tree.setObjectName("lobbyServers")
        self.servers_tree.setHeaderHidden(True)
        self.servers_tree.setColumnCount(3)
        self.servers_tree.setRootIsDecorated(False)
        self.servers_tree.setSelectionMode(QAbstractItemView.NoSelection)
        self.servers_tree.setFocusPolicy(Qt.NoFocus)
        header = self.servers_tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        servers_column.addWidget(self.servers_tree, 1)
        self.no_servers = QFrame()
        no_servers_layout = QHBoxLayout(self.no_servers)
        no_servers_layout.setContentsMargins(0, 0, 0, 0)
        no_servers_layout.addWidget(
            plain_label(gettext("No lobby servers yet"))
        )
        self.add_server_button = QPushButton(gettext("Add a server…"))
        self.add_server_button.clicked.connect(self.on_add_server)
        no_servers_layout.addWidget(self.add_server_button)
        no_servers_layout.addStretch(1)
        servers_column.addWidget(self.no_servers)

        games_column = QVBoxLayout()
        columns.addLayout(games_column, 3)
        games_column.addWidget(plain_label(gettext("Games"), "sectionTitle"))
        self.games_tree = QTreeWidget()
        self.games_tree.setObjectName("lobbyGames")
        self.games_tree.setColumnCount(5)
        self.games_tree.setHeaderLabels(
            [
                gettext("Game"),
                gettext("Host"),
                gettext("Players"),
                gettext("Server"),
                "",
            ]
        )
        self.games_tree.setRootIsDecorated(False)
        self.games_tree.setSelectionMode(QAbstractItemView.SingleSelection)
        header = self.games_tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, 5):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        games_column.addWidget(self.games_tree, 1)
        self.no_games = plain_label(gettext("No games waiting for players"))
        self.no_games.setObjectName("lobbyEmpty")
        games_column.addWidget(self.no_games)

        layout.addWidget(plain_label(gettext("Activity"), "sectionTitle"))
        self.activity = QPlainTextEdit()
        self.activity.setObjectName("lobbyActivity")
        self.activity.setReadOnly(True)
        self.activity.setMaximumBlockCount(200)
        self.activity.setFixedHeight(
            self.activity.fontMetrics().lineSpacing() * 4 + 12
        )
        layout.addWidget(self.activity)

        # Counts down "retrying in N s" while a server can't be reached.
        self.countdown = QTimer(self)
        self.countdown.setInterval(1000)
        self.countdown.timeout.connect(self.refresh)

        for line in netplay.activity_log:
            self.add_activity(line)
        netplay.browser_listeners.append(self.refresh)
        netplay.activity_listeners.append(self.add_activity)
        self.refresh()

    def restyle(self):
        if fsui.theme_variant == "modern":
            self.setStyleSheet(modern_theme.render("""
                QFrame#lobbyBrowser { background: @surface@; }
                QLabel#lobbyEmpty { color: @muted@; }
            """))
        else:
            self.setStyleSheet("""
                QFrame#lobbyBrowser { background: palette(window); }
            """)

    def shutdown(self):
        self.countdown.stop()
        theme_applied.disconnect(self.restyle)
        if self.refresh in self.netplay.browser_listeners:
            self.netplay.browser_listeners.remove(self.refresh)
        if self.add_activity in self.netplay.activity_listeners:
            self.netplay.activity_listeners.remove(self.add_activity)

    # --- Rendering ------------------------------------------------------------

    def refresh(self):
        browser = self.netplay.browser
        servers = browser.servers()
        now = browser.now()
        self._render_servers(servers, now)
        self._render_games(browser.games())
        waiting = any(s.state == UNREACHABLE for s in servers)
        if waiting and not self.countdown.isActive():
            self.countdown.start()
        elif not waiting:
            self.countdown.stop()

    def _render_servers(self, servers, now):
        tree = self.servers_tree
        tree.clear()
        for server in servers:
            dot = DOT_ONLINE if server.state == ONLINE else DOT_OFFLINE
            item = QTreeWidgetItem(
                [f"{dot} {server.title}", server_status(server, now), ""]
            )
            item.setData(0, Qt.UserRole, server.key)
            if server.error and server.state != ONLINE:
                item.setToolTip(1, server.error)
            tree.addTopLevelItem(item)
            if server.state in (UNREACHABLE, NO_LISTING):
                button = QPushButton(gettext("Retry"))
                button.setToolTip(gettext("Try this server again now"))
                button.clicked.connect(
                    lambda checked=False, key=server.key: self.on_retry(key)
                )
                tree.setItemWidget(item, 2, button)
            online = server.online
            if online:
                me = self.netplay.browser.my_name()
                names = [
                    f"{name} ({gettext('you')})" if name == me else name
                    for name in online
                ]
                child = QTreeWidgetItem(
                    ["    " + gettext("Online: ") + ", ".join(names), "", ""]
                )
                child.setFirstColumnSpanned(True)
                tree.addTopLevelItem(child)
        self.no_servers.setVisible(not servers)
        tree.setVisible(bool(servers))

    def _render_games(self, games):
        tree = self.games_tree
        selected = self.selected_game_id()
        tree.clear()
        for game in games:
            item = QTreeWidgetItem(
                [
                    game.title,
                    game.host,
                    game_players(game),
                    game.server.short_title,
                    game_action(game),
                ]
            )
            item.setData(0, Qt.UserRole, (game.server.key, game.id))
            if not game.joinable:
                item.setDisabled(True)
            tree.addTopLevelItem(item)
            if game.id == selected:
                tree.setCurrentItem(item)
        self.no_games.setVisible(not games)

    def selected_game_id(self):
        item = self.games_tree.currentItem()
        if item is None:
            return None
        return item.data(0, Qt.UserRole)[1]

    def add_activity(self, line):
        when, text, warning = line
        stamp = time.strftime("%H:%M", time.localtime(when))
        self.activity.appendPlainText(f"{stamp}  {text}")

    # --- Actions ----------------------------------------------------------------

    def on_retry(self, key):
        self.netplay.browser.retry(key)

    def on_add_server(self):
        if self.open_settings is not None:
            self.open_settings()
