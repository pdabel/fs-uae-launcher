"""The Net Play tab's lobby browser: servers, the games on them, and an
activity log. See "UX" in docs/netplay-rooms-design.md.

Names, titles and server names come from other users, so every one of
them is shown as plain text.
"""

import time

import fsui
import qtawesome as qta
from fsui.qt import modern_theme
from fsui.qt.qt import theme_applied
from fsui.qt import (
    Qt,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTimer,
    QVBoxLayout,
)
from qtpy.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)
from launcher.i18n import gettext
from launcher.launcher_settings import LauncherSettings
from launcher.netplay.lobby_browser import (
    CONNECTING,
    LOCAL,
    LOCAL_HOST,
    NO_LISTING,
    ONLINE,
    UNREACHABLE,
)
from launcher.netplay.lobby_servers import parse_lobby
from launcher.netplay.netplay import HOSTING, LAST_HOST_SERVER
from launcher.option import Option

# Status dots: filled when the server answers.
DOT_ONLINE = "●"
DOT_OFFLINE = "○"


# Players a game can have, as the lobby allows.
MIN_PLAYERS = 2
MAX_PLAYERS = 6

# The settings that say whether a game is loaded, and what it's called.
GAME_SETTINGS = (Option.CONFIG_NAME, "parent_uuid", "config_path")


def has_game():
    """Whether a game is loaded to host, rather than an empty config."""
    return bool(
        LauncherSettings.get("parent_uuid")
        or LauncherSettings.get("config_path")
    )


def plain_label(text="", object_name=None):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
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
    def __init__(
        self, netplay, open_settings=None, show_info=None, parent=None
    ):
        super().__init__(parent)
        self.netplay = netplay
        self.open_settings = open_settings
        self.show_info = show_info
        self.setObjectName("lobbyBrowser")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        header = QHBoxLayout()
        layout.addLayout(header)
        header.addWidget(plain_label(gettext("Net Play"), "sectionTitle"))
        header.addStretch(1)
        self.info_button = QPushButton()
        self.info_button.setToolTip(gettext("Show instructions for Netplay"))
        self.info_button.setAccessibleName(gettext("Netplay instructions"))
        self.info_button.setFlat(True)
        self.info_button.clicked.connect(self.on_info)
        self.info_button.setVisible(show_info is not None)
        header.addWidget(self.info_button)
        self.restyle()
        theme_applied.connect(self.restyle)

        # Browsing, or the game this launcher is in.
        self.pages = QStackedWidget()
        layout.addWidget(self.pages, 1)
        self.browse_page = QWidget()
        browse = QVBoxLayout(self.browse_page)
        browse.setContentsMargins(0, 0, 0, 0)
        self.pages.addWidget(self.browse_page)

        columns = QHBoxLayout()
        columns.setSpacing(20)
        browse.addLayout(columns, 1)

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
        self.servers_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self.servers_tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        servers_header = self.servers_tree.header()
        servers_header.setStretchLastSection(False)
        servers_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2):
            servers_header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
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
        self.games_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        games_header = self.games_tree.header()
        games_header.setStretchLastSection(False)
        games_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 5):
            games_header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        games_column.addWidget(self.games_tree, 1)
        self.no_games = plain_label(gettext("No games waiting for players"))
        self.no_games.setObjectName("lobbyEmpty")
        games_column.addWidget(self.no_games)

        buttons = QHBoxLayout()
        browse.addLayout(buttons)
        self.host_button = QPushButton()
        self.host_button.clicked.connect(self.on_host)
        buttons.addWidget(self.host_button)
        self.join_by_id_button = QPushButton(gettext("Join by ID\u2026"))
        self.join_by_id_button.setToolTip(
            gettext("Join a game that isn't listed, with the ID its host gave")
        )
        self.join_by_id_button.clicked.connect(self.on_join_by_id)
        buttons.addWidget(self.join_by_id_button)
        buttons.addStretch(1)

        # This computer's lobby, while it runs between games.
        self.lobby_row = QFrame()
        lobby_row = QHBoxLayout(self.lobby_row)
        lobby_row.setContentsMargins(0, 0, 0, 0)
        self.lobby_label = plain_label()
        lobby_row.addWidget(self.lobby_label, 1)
        self.copy_address_button = QPushButton(gettext("Copy address"))
        self.copy_address_button.setToolTip(
            gettext("Copy the address players add to their server list")
        )
        self.copy_address_button.clicked.connect(self.on_copy_address)
        lobby_row.addWidget(self.copy_address_button)
        self.stop_lobby_button = QPushButton(gettext("Stop lobby"))
        self.stop_lobby_button.clicked.connect(self.on_stop_lobby)
        lobby_row.addWidget(self.stop_lobby_button)
        browse.addWidget(self.lobby_row)

        self.game_page = QWidget()
        game = QVBoxLayout(self.game_page)
        game.setContentsMargins(0, 0, 0, 0)
        self.pages.addWidget(self.game_page)
        self.game_heading = plain_label("", "sectionTitle")
        self.game_heading.setWordWrap(True)
        game.addWidget(self.game_heading)
        self.slot_list = QListWidget()
        self.slot_list.setObjectName("lobbySlots")
        self.slot_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self.slot_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        game.addWidget(self.slot_list, 1)
        self.game_online = plain_label()
        self.game_online.setWordWrap(True)
        game.addWidget(self.game_online)
        address_row = QHBoxLayout()
        game.addLayout(address_row)
        self.game_address = plain_label()
        address_row.addWidget(self.game_address)
        self.game_copy_address_button = QPushButton(gettext("Copy address"))
        self.game_copy_address_button.clicked.connect(self.on_copy_address)
        address_row.addWidget(self.game_copy_address_button)
        address_row.addStretch(1)
        game_buttons = QHBoxLayout()
        game.addLayout(game_buttons)
        self.recheck_button = QPushButton(gettext("Re-check"))
        self.recheck_button.setToolTip(
            gettext(
                "Apply the game's config again, for example after adding "
                "missing files"
            )
        )
        self.recheck_button.clicked.connect(self.on_recheck)
        game_buttons.addWidget(self.recheck_button)
        self.leave_button = QPushButton(gettext("Leave"))
        self.leave_button.clicked.connect(self.on_leave)
        game_buttons.addWidget(self.leave_button)
        self.copy_game_id_button = QPushButton(gettext("Copy game ID"))
        self.copy_game_id_button.setToolTip(
            gettext("This game isn't listed: players join it by its ID")
        )
        self.copy_game_id_button.clicked.connect(self.on_copy_game_id)
        game_buttons.addWidget(self.copy_game_id_button)
        self.game_stop_lobby_button = QPushButton(gettext("Stop lobby"))
        self.game_stop_lobby_button.clicked.connect(self.on_stop_lobby)
        game_buttons.addWidget(self.game_stop_lobby_button)
        game_buttons.addStretch(1)
        self.game_status = plain_label()
        self.game_status.setWordWrap(True)
        game.addWidget(self.game_status)

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
        netplay.session_listeners.append(self.on_session)
        LauncherSettings.add_listener(self)
        self.update_host_button()
        self.refresh()
        self.on_session(netplay.session)

    def restyle(self):
        self.info_button.setIcon(
            qta.icon("fa5s.info-circle", color=modern_theme.palette().icon)
        )
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
        if self.on_session in self.netplay.session_listeners:
            self.netplay.session_listeners.remove(self.on_session)
        LauncherSettings.remove_listener(self)

    def on_setting(self, key, value):
        if key in GAME_SETTINGS:
            self.update_host_button()

    def update_host_button(self):
        if has_game():
            title = LauncherSettings.get(Option.CONFIG_NAME).strip()
            metrics = self.host_button.fontMetrics()
            title = metrics.elidedText(title, Qt.TextElideMode.ElideRight, 240)
            self.host_button.setText(
                gettext("Host game: {0}\u2026").format(title)
            )
            self.host_button.setEnabled(True)
            self.host_button.setToolTip(
                gettext("Host this game and wait for players to join")
            )
        else:
            self.host_button.setText(gettext("Host game\u2026"))
            self.host_button.setEnabled(False)
            self.host_button.setToolTip(gettext("Choose a game first"))

    # --- Rendering ------------------------------------------------------------

    def refresh(self):
        browser = self.netplay.browser
        servers = browser.servers()
        now = browser.now()
        self._render_servers(servers, now)
        self._render_games(browser.games())
        self._render_lobby_row()
        if self.pages.currentWidget() is self.game_page:
            self.on_session()
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
            item.setData(0, Qt.ItemDataRole.UserRole, server.key)
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
            item.setData(
                0, Qt.ItemDataRole.UserRole, (game.server.key, game.id)
            )
            if not game.joinable:
                item.setDisabled(True)
            tree.addTopLevelItem(item)
            if game.joinable:
                button = QPushButton(gettext("Join"))
                button.setToolTip(
                    gettext("Join {0}, hosted by {1}").format(
                        game.title, game.host
                    )
                )
                button.clicked.connect(
                    lambda checked=False, game=game: self.on_join(game)
                )
                tree.setItemWidget(item, 4, button)
            if game.id == selected:
                tree.setCurrentItem(item)
        self.no_games.setVisible(not games)

    def _render_lobby_row(self):
        server = self.netplay.running_local_lobby()
        self.lobby_row.setVisible(server is not None)
        if server is None:
            return
        address = self.netplay.local_lobby_address()
        if address:
            text = gettext(
                "Your lobby is running. Players reach you at {0}"
            ).format(address)
        else:
            text = gettext("Your lobby is running on port {0}").format(
                server.port
            )
        self.lobby_label.setText(text)
        self.copy_address_button.setEnabled(bool(address))

    def local_online(self):
        """Who is in this computer's lobby, besides this launcher."""
        local = self.netplay.browser.server(LOCAL)
        if local is None:
            return []
        me = self.netplay.browser.my_name()
        online = list(local.online)
        if me in online:
            online.remove(me)
        return online

    def selected_game_id(self):
        item = self.games_tree.currentItem()
        if item is None:
            return None
        return item.data(0, Qt.ItemDataRole.UserRole)[1]

    def on_session(self, session=None):
        """Show the game this launcher is in, or go back to browsing."""
        netplay = self.netplay
        session = netplay.session
        if session is None and netplay.joining is None:
            self.pages.setCurrentWidget(self.browse_page)
            return
        self.pages.setCurrentWidget(self.game_page)
        hosted_here = bool(
            session is not None and session.is_host and netplay.session_hosted
        )
        address = netplay.local_lobby_address() if hosted_here else None
        online = self.local_online() if hosted_here else []
        self.game_online.setVisible(bool(online))
        self.game_online.setText(
            gettext("Online in your lobby: ") + ", ".join(online)
        )
        self.game_address.setVisible(bool(address))
        self.game_copy_address_button.setVisible(bool(address))
        if address:
            self.game_address.setText(
                gettext("Players reach you at {0}").format(address)
            )
        self.game_stop_lobby_button.setVisible(hosted_here)
        self.copy_game_id_button.setVisible(
            bool(
                session is not None
                and session.is_host
                and not netplay.session_listed
            )
        )
        if session is None:
            if netplay.joining == HOSTING:
                self.game_heading.setText(gettext("Creating the game\u2026"))
            else:
                self.game_heading.setText(gettext("Joining\u2026"))
            self.slot_list.clear()
            self.game_status.setText("")
            self.recheck_button.setEnabled(False)
            self.leave_button.setText(gettext("Leave"))
            return
        self.game_heading.setText(self.game_heading_text(session))
        self.slot_list.clear()
        self.slot_list.addItems(session.slot_lines())
        self.game_status.setText(session.status_line())
        self.recheck_button.setEnabled(not session.started)
        self.leave_button.setText(
            gettext("End game") if session.is_host else gettext("Leave")
        )

    def game_heading_text(self, session):
        snapshot = session.snapshot or {}
        title = (
            self.netplay.session_title
            or snapshot.get("title")
            or gettext("Game {0}").format(session.game_id[:8])
        )
        if session.is_host:
            host = gettext("you")
        else:
            slots = snapshot.get("slots") or []
            host = (slots[0].get("tag") if slots else None) or "?"
        server = self.netplay.session_server
        if server:
            return gettext("{0}, hosted by {1} on {2}").format(
                title, host, server
            )
        return gettext("{0}, hosted by {1}").format(title, host)

    def add_activity(self, line):
        when, text, warning = line
        stamp = time.strftime("%H:%M", time.localtime(when))
        self.activity.appendPlainText(f"{stamp}  {text}")

    # --- Actions ----------------------------------------------------------------

    def on_join(self, game):
        self.netplay.join_game(
            game.server.host,
            game.server.port,
            game.id,
            title=game.title,
            server=game.server.short_title,
        )

    def on_join_by_id(self):
        choices = [
            s.key for s in self.netplay.browser.servers() if s.key != LOCAL
        ]
        local = self.netplay.browser.server(LOCAL)
        if local is not None:
            choices.insert(0, gettext("This computer"))
        answer = JoinByIdDialog.get(self, choices)
        if answer is None:
            return
        server, game_id = answer
        if local is not None and server == gettext("This computer"):
            host, port, label = LOCAL_HOST, local.port, server
        else:
            try:
                host, port = parse_lobby(server)
            except ValueError:
                self.netplay.activity(
                    gettext("{0} is not host or host:port").format(server),
                    True,
                )
                return
            label = server
        self.netplay.join_game(host, port, game_id, server=label)

    def on_host(self):
        if not has_game():
            return
        browser = self.netplay.browser
        address = LauncherSettings.get(Option.NETPLAY_PUBLIC_ADDRESS).strip()
        local = gettext("This computer")
        if address:
            local += f" ({address})"
        choices = [(LOCAL, local)] + [
            (s.key, s.title)
            for s in browser.servers()
            if s.key != LOCAL and s.state == ONLINE
        ]
        last = LauncherSettings.get(LAST_HOST_SERVER)
        title = LauncherSettings.get(Option.CONFIG_NAME).strip()
        answer = HostGameDialog.get(self, title, choices, last)
        if answer is None:
            return
        server, players, listed = answer
        self.netplay.host_game(server, players, listed)

    def on_copy_address(self):
        address = self.netplay.local_lobby_address()
        if address:
            QApplication.clipboard().setText(address)
            self.netplay.activity(
                gettext(
                    "Copied {0}: players add it to their server list"
                ).format(address)
            )

    def on_copy_game_id(self):
        session = self.netplay.session
        if session is not None:
            QApplication.clipboard().setText(session.game_id)
            self.netplay.activity(
                gettext("Copied the game ID: players use Join by ID\u2026")
            )

    def on_stop_lobby(self):
        self.netplay.stop_lobby()
        self.refresh()

    def on_recheck(self):
        self.netplay.recheck()

    def on_leave(self):
        self.netplay.leave_game()

    def on_retry(self, key):
        self.netplay.browser.retry(key)

    def on_info(self):
        if self.show_info is not None:
            self.show_info()

    def on_add_server(self):
        if self.open_settings is not None:
            self.open_settings()


class JoinByIdDialog(QDialog):
    """Asks for the lobby and the ID of a game that isn't listed."""

    def __init__(self, parent, servers):
        super().__init__(parent)
        self.setWindowTitle(gettext("Join by ID"))
        layout = QFormLayout(self)
        self.server = QComboBox()
        self.server.setEditable(True)
        self.server.addItems(servers)
        self.server.setToolTip(gettext("host or host:port"))
        layout.addRow(gettext("Server:"), self.server)
        self.game_id = QLineEdit()
        self.game_id.setPlaceholderText(gettext("The ID the host copied"))
        layout.addRow(gettext("Game ID:"), self.game_id)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            gettext("Join")
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def answer(self):
        server = self.server.currentText().strip()
        game_id = self.game_id.text().strip()
        if not server or not game_id:
            return None
        return server, game_id

    @staticmethod
    def get(parent, servers):
        """(server, game id), or None if cancelled or left blank."""
        dialog = JoinByIdDialog(parent, servers)
        try:
            if dialog.exec():
                return dialog.answer()
            return None
        finally:
            dialog.deleteLater()


class HostGameDialog(QDialog):
    """Where to host the loaded game, for how many, and whether to list it."""

    def __init__(self, parent, title, servers, last=None):
        super().__init__(parent)
        self.setWindowTitle(gettext("Host {0}").format(title))
        layout = QFormLayout(self)
        self.server = QComboBox()
        for key, label in servers:
            self.server.addItem(label, key)
        index = self.server.findData(last)
        self.server.setCurrentIndex(max(index, 0))
        layout.addRow(gettext("Server:"), self.server)
        self.players = QComboBox()
        for n in range(MIN_PLAYERS, MAX_PLAYERS + 1):
            self.players.addItem(str(n), n)
        layout.addRow(gettext("Players:"), self.players)
        self.listed = QCheckBox(gettext("List this game"))
        self.listed.setChecked(True)
        self.listed.setToolTip(
            gettext(
                "Anyone browsing the server sees it and can join. Untick to "
                "share its ID with the players instead"
            )
        )
        layout.addRow(self.listed)
        note = plain_label(
            gettext("Starts when every player has joined and is ready.")
        )
        layout.addRow(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            gettext("Host")
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def answer(self):
        return (
            self.server.currentData(),
            self.players.currentData(),
            self.listed.isChecked(),
        )

    @staticmethod
    def get(parent, title, servers, last=None):
        """(server key, players, listed), or None if cancelled."""
        dialog = HostGameDialog(parent, title, servers, last)
        try:
            if dialog.exec():
                return dialog.answer()
            return None
        finally:
            dialog.deleteLater()
