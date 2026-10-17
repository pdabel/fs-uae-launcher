import fsui
import qtawesome as qta
from fsui.qt import (
    Qt, QSize, QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QSplitter, QStyle, QToolButton, QVBoxLayout,
    QWidget, QPoint,
)
from launcher.i18n import gettext
from launcher.launcher_settings import LauncherSettings
from launcher.ui.launch import LaunchGroup


class Dashboard(fsui.Panel):
    PAGES = (
        ("Overview", QStyle.SP_ComputerIcon),
        ("Floppy drives", QStyle.SP_DriveFDIcon),
        ("CD-ROM drives", QStyle.SP_DriveCDIcon),
        ("Hard drives", QStyle.SP_DriveHDIcon),
        ("ROM & memory", QStyle.SP_FileDialogDetailedView),
        ("Controllers", QStyle.SP_DesktopIcon),
        ("Expansions", QStyle.SP_FileDialogContentsView),
        ("Advanced", QStyle.SP_FileDialogListView),
    )

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self._restore_library_after_quick = False
        self.widget().setObjectName("dashboard")
        self.set_min_size((1000, 720))
        self.widget().setStyleSheet("""
            QWidget#dashboard { background: #171923; }
            QFrame#navigation { background: #1c1e2b;
                border-right: 1px solid #303447; }
            QLabel#brand { font-size: 23px; font-weight: 700; color: #f5f7fc; }
            QLabel#brandCaption, QLabel#eyebrow { color: #929db6;
                font-size: 11px; }
            QLabel#pageTitle { color: #f5f7fc; font-size: 25px;
                font-weight: 600; }
            QLabel#sectionTitle { color: #edf0f7; font-size: 15px;
                font-weight: 600; }
            QLabel#badge { background: #173c3a; color: #69d6ae;
                padding: 5px 9px; border-radius: 4px; font-size: 11px; }
            QLabel#configurationName { color: #b9c5da; font-size: 13px; }
            QPushButton[nav="true"] { background: transparent;
                color: #aeb8ce; border: 0; border-radius: 4px;
                text-align: left; padding: 11px 14px; }
            QPushButton[nav="true"]:hover { background: #282d40; color: white; }
            QPushButton[nav="true"]:checked { background: #253e54;
                color: #73cef8; border-left: 3px solid #46b7ee; }
            QFrame#topbar { border-bottom: 1px solid #303447; }
            QFrame#launchbar { background: #212431;
                border-top: 1px solid #363d51; }
            QFrame#library { background: #212431; }
            QFrame#editor { background: #212431; }
            QToolButton { background: #292d3e; color: #dce5f5;
                border: 1px solid #40485e; border-radius: 4px; padding: 8px; }
            QToolButton:hover { background: #3b445d; }
            QToolButton:checked { background: #254f69; border-color: #46b7ee; }
            QPushButton#launchButton { background: #36b4e5; color: #101d28;
                border: 1px solid #5dc8ef; font-weight: 700;
                padding: 10px 24px; }
            QPushButton#launchButton:hover { background: #72d2f2; }
            QPushButton#launchButton:disabled { background: #303649;
                color: #737e96; border-color: #454d64; }
            QSplitter::handle { background: #171923; }
            QSplitter::handle:hover { background: #46b7ee; }
            QScrollArea { border: 0; background: #212431; }
        """)
        root = QHBoxLayout(self.widget())
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.navigation = self._navigation()
        root.addWidget(self.navigation)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 0, 24, 0)
        body_layout.setSpacing(16)
        root.addWidget(body, 1)
        body_layout.addWidget(self._topbar())

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(16)
        self.library = self._section(gettext("Library"), "library")
        self.library.setMinimumWidth(300)
        self.library.layout().addWidget(self._scroll(owner.books[1]), 1)
        self.splitter.addWidget(self.library)

        self.editor = self._section(gettext("Configuration"), "editor")
        self.editor.setMinimumWidth(380)
        self.editor_scroll = self._scroll(owner.books[2])
        self.editor.layout().addWidget(self.editor_scroll, 1)
        self.splitter.addWidget(self.editor)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setSizes([450, 850])
        body_layout.addWidget(self.splitter, 1)

        self.media = QWidget()
        media_layout = QHBoxLayout(self.media)
        media_layout.setContentsMargins(0, 0, 0, 0)
        media_layout.setSpacing(16)
        if owner.screenshots_panel is not None:
            screenshots = owner.screenshots_panel.widget()
            screenshots.setMinimumWidth(230)
            media_layout.addWidget(screenshots, 1)
            screenshots.show()
            information = owner.game_info_panel.widget()
            information.setMinimumWidth(420)
            media_layout.addWidget(information, 2)
            information.show()
        self.media.setFixedHeight(220)
        body_layout.addWidget(self.media)
        body_layout.addWidget(self._launchbar())
        status = owner.status_bar.widget()
        status.setFixedHeight(30)
        body_layout.addWidget(status)
        status.show()
        body_layout.setSpacing(12)
        LauncherSettings.add_listener(self)
        owner.closed.connect(self._remove_listener)
        self.on_setting("config_name", LauncherSettings.get("config_name"))
        self._show_page(0)

    def _icon(self, standard_icon):
        names = {
            QStyle.SP_ComputerIcon: "fa5s.home",
            QStyle.SP_DriveFDIcon: "fa5s.save",
            QStyle.SP_DriveCDIcon: "fa5s.compact-disc",
            QStyle.SP_DriveHDIcon: "fa5s.hdd",
            QStyle.SP_FileDialogDetailedView: "fa5s.sliders-h",
            QStyle.SP_DesktopIcon: "fa5s.gamepad",
            QStyle.SP_FileDialogContentsView: "fa5s.th-large",
            QStyle.SP_FileDialogListView: "fa5s.code",
            QStyle.SP_DriveNetIcon: "fa5s.network-wired",
            QStyle.SP_TitleBarMenuButton: "fa5s.ellipsis-h",
            QStyle.SP_MediaPlay: "fa5s.play",
        }
        return qta.icon(names[standard_icon], color="#9bcce2")

    def _navigation(self):
        frame = QFrame()
        frame.setObjectName("navigation")
        frame.setFixedWidth(216)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 26, 16, 22)
        layout.setSpacing(6)
        brand = QLabel("FS-UAE")
        brand.setObjectName("brand")
        layout.addWidget(brand)
        caption = QLabel(gettext("AMIGA LAUNCHER"))
        caption.setObjectName("brandCaption")
        layout.addWidget(caption)
        layout.addSpacing(30)
        self.nav_group = QButtonGroup(frame)
        self.nav_buttons = []
        for index, (title, icon) in enumerate(self.PAGES):
            button = QPushButton(
                self._icon(icon), gettext(title).replace("&", "&&")
            )
            button.setProperty("nav", True)
            button.setCheckable(True)
            button.setMinimumHeight(44)
            button.setIconSize(QSize(20, 20))
            button.setToolTip(gettext(title))
            self.nav_group.addButton(button, index)
            layout.addWidget(button)
            self.nav_buttons.append(button)
        self.nav_group.idClicked.connect(self._show_page)
        self.nav_buttons[0].setChecked(True)
        layout.addStretch(1)
        for title, icon, callback in (
            ("Net play", QStyle.SP_DriveNetIcon, self.owner.on_net_play),
            ("Settings", QStyle.SP_FileDialogDetailedView,
             self.owner.on_settings_button),
            ("Tools & account", QStyle.SP_TitleBarMenuButton, self._tools),
        ):
            button = QPushButton(
                self._icon(icon), gettext(title).replace("&", "&&")
            )
            button.setProperty("nav", True)
            button.setMinimumHeight(42)
            button.clicked.connect(callback)
            layout.addWidget(button)
        return frame

    def _topbar(self):
        frame = QFrame()
        frame.setObjectName("topbar")
        frame.setMinimumHeight(96)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 16, 0, 16)
        titles = QVBoxLayout()
        titles.setSpacing(3)
        eyebrow = QLabel(gettext("WORKSPACE  /  AMIGA"))
        eyebrow.setObjectName("eyebrow")
        titles.addWidget(eyebrow)
        self.page_title = QLabel(gettext("Overview"))
        self.page_title.setObjectName("pageTitle")
        titles.addWidget(self.page_title)
        layout.addLayout(titles)
        layout.addStretch(1)
        self.configuration_name = QLabel()
        self.configuration_name.setObjectName("configurationName")
        self.configuration_name.setMaximumWidth(260)
        layout.addWidget(self.configuration_name)
        layout.addSpacing(12)
        badge = QLabel(gettext("LOCAL WORKSPACE"))
        badge.setObjectName("badge")
        badge.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        layout.addWidget(badge)
        layout.addSpacing(12)
        self.library_toggle = self._tool(
            QStyle.SP_FileDialogContentsView, gettext("Show library")
        )
        self.library_toggle.setCheckable(True)
        self.library_toggle.setChecked(True)
        self.library_toggle.toggled.connect(self._toggle_library)
        layout.addWidget(self.library_toggle)
        self.quick_toggle = self._tool(
            QStyle.SP_FileDialogDetailedView, gettext("Quick settings")
        )
        self.quick_toggle.setCheckable(True)
        self.quick_toggle.toggled.connect(self._toggle_quick_settings)
        layout.addWidget(self.quick_toggle)
        return frame

    def _tool(self, icon, tooltip):
        button = QToolButton()
        button.setIcon(self._icon(icon))
        button.setIconSize(QSize(20, 20))
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setFixedSize(40, 40)
        return button

    def _section(self, title, name):
        frame = QFrame()
        frame.setObjectName(name)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 16, 14, 12)
        layout.setSpacing(12)
        label = QLabel(title)
        label.setObjectName("sectionTitle")
        layout.addWidget(label)
        return frame

    def _scroll(self, panel):
        area = QScrollArea()
        area.setWidgetResizable(True)
        widget = panel.widget()
        width, height = panel.get_min_width(), panel.get_min_height()
        widget.setMinimumSize(max(280, width), max(100, height))
        area.setWidget(widget)
        widget.show()
        return area

    def _launchbar(self):
        frame = QFrame()
        frame.setObjectName("launchbar")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(16, 10, 16, 10)
        self.launch_host = fsui.Panel(self)
        self.launch_host.layout = fsui.VerticalLayout()
        self.launch_group = LaunchGroup(self.launch_host, self.owner.gsc)
        self.launch_host.layout.add(self.launch_group, fill=True, expand=True)
        self.launch_host.widget().setMinimumHeight(48)
        for button in self.launch_host.widget().findChildren(QPushButton):
            if button.text().strip() == gettext("Start"):
                button.setObjectName("launchButton")
                button.setText(gettext("Launch Amiga"))
                button.setIcon(self._icon(QStyle.SP_MediaPlay))
        layout.addWidget(self.launch_host.widget(), 1)
        self.launch_host.widget().show()
        return frame

    def _show_page(self, index):
        self.owner.books[2].set_page(index)
        self.page_title.setText(gettext(self.PAGES[index][0]))
        self.nav_buttons[index].setChecked(True)
        width = self.owner.books[2].get_min_width()
        height = self.owner.books[2].get_min_height()
        self.owner.books[2].widget().setMinimumSize(width, height)

    def _tools(self):
        menu = self.owner.create_menu()
        menu.qmenu.exec(self.navigation.mapToGlobal(QPoint(16, self.navigation.height() - 60)))

    def _toggle_library(self, checked):
        if checked and self.widget().width() < 1400:
            self.quick_toggle.setChecked(False)
        self.library.setVisible(checked)

    def _toggle_quick_settings(self, checked):
        if not hasattr(self, "quick_area"):
            self.quick_area = self._scroll(self.owner.quick_settings_panel)
            self.quick_area.setMinimumWidth(240)
            self.quick_area.setMaximumWidth(300)
            self.splitter.addWidget(self.quick_area)
        self.quick_area.setVisible(checked)
        if checked and self.widget().width() < 1400:
            self._restore_library_after_quick = self.library_toggle.isChecked()
            self.library_toggle.setChecked(False)
        elif not checked and self._restore_library_after_quick:
            self._restore_library_after_quick = False
            self.library_toggle.setChecked(True)

    def on_resize(self):
        super().on_resize()
        if hasattr(self, "media"):
            self.media.setVisible(self.widget().height() >= 820)
            if self.widget().width() < 1400 and self.quick_toggle.isChecked():
                if self.library_toggle.isChecked():
                    self._restore_library_after_quick = True
                    self.library_toggle.setChecked(False)

    def on_setting(self, key, value):
        if key == "config_name":
            metrics = self.configuration_name.fontMetrics()
            self.configuration_name.setText(
                metrics.elidedText(value, Qt.ElideRight, 250)
            )
            self.configuration_name.setToolTip(value)

    def _remove_listener(self):
        LauncherSettings.remove_listener(self)