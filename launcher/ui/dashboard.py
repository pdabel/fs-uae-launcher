import fsui
from fsui.qt import modern_theme
from fsui.qt.qt import theme_applied
from fsui.qt import (
    Qt, QSize, QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QSplitter, QStyle, QToolButton, QVBoxLayout,
    QWidget, QPoint, QStackedWidget,
)
from launcher.i18n import gettext
from launcher.launcher_settings import LauncherSettings
from launcher.ui.launch import LaunchGroup
from launcher.ui.navigation_icons import navigation_icon
from launcher.ui.play_tile import PlayTile


MODERN_STYLESHEET = """
            QWidget#dashboard { background: @window@; }
            QFrame#navigation { background: @nav@;
                border-right: 1px solid @nav_border@; }
            QLabel#brand { font-size: 23px; font-weight: 700; color: @brand@; }
            QLabel#brandCaption, QLabel#eyebrow { color: @caption@;
                font-size: 11px; }
            QLabel#pageTitle { color: @brand@; font-size: 25px;
                font-weight: 600; }
            QLabel#sectionTitle { color: @text@; font-size: 15px;
                font-weight: 600; }
            QLabel#badge { background: @success_bg@; color: @success@;
                padding: 5px 9px; border-radius: @radius_small@; font-size: 11px; }
            QLabel#configurationName { color: @nav_text@; font-size: 13px; }
            QPushButton[nav="true"] { background: transparent;
                color: @nav_text@; border: 0; border-radius: @radius_small@;
                text-align: left; padding: 11px 14px; }
            QPushButton[nav="true"]:hover { background: @nav_hover@; color: @brand@; }
            QPushButton[nav="true"]:checked { background: @pressed@;
                color: @accent_soft@; border-left: 3px solid @accent@; }
            QFrame#topbar { border-bottom: 1px solid @nav_border@; }
            QFrame#launchbar { background: @surface@;
                border-top: 1px solid @border@; }
            QFrame#library { background: @surface@; }
            QFrame#editor { background: @surface@; }
            QFrame#playTile { background: @raised@;
                border: 1px solid @border_strong@; border-radius: @radius@; }
            QLabel#playTitle { color: @brand@; font-size: 21px;
                font-weight: 700; }
            QLabel#playSubtitle { color: @muted@; font-size: 12px; }
            QPushButton#playButton { background: @accent@; color: @accent_text@;
                border: 1px solid @accent_hover@; border-radius: @radius@;
                font-size: 17px; font-weight: 700; padding: 10px 28px; }
            QPushButton#playButton:hover { background: @accent_hover@; }
            QPushButton#playButton:disabled { background: @launch_disabled@;
                color: @disabled_text@; border-color: @border_strong@; }
            QPushButton#editButton:checked { background: @pressed@;
                border-color: @accent@; color: @accent_soft@; }
            QToolButton { background: @raised@; color: @text@;
                border: 1px solid @border_strong@; border-radius: @radius_small@; padding: 8px; }
            QToolButton:hover { background: @hover@; }
            QToolButton:checked { background: @highlight@; border-color: @accent@; }
            QPushButton#launchButton { background: @accent@; color: @accent_text@;
                border: 1px solid @accent_hover@; font-weight: 700;
                padding: 10px 24px; }
            QPushButton#launchButton:hover { background: @accent_hover@; }
            QPushButton#launchButton:disabled { background: @launch_disabled@;
                color: @disabled_text@; border-color: @border_strong@; }
            QSplitter::handle { background: @window@; }
            QSplitter::handle:hover { background: @accent@; }
            QScrollArea { border: 0; background: @surface@; }
        """

PALETTE_STYLESHEET = """
                QWidget#dashboard, QFrame#navigation {
                    background: palette(window); color: palette(window-text); }
                QFrame#navigation { border-right: 2px solid palette(shadow); }
                QLabel#brand { font-size: 23px; font-weight: 700; }
                QLabel#brandCaption, QLabel#eyebrow { font-size: 11px; }
                QLabel#pageTitle { font-size: 25px; font-weight: 600; }
                QLabel#sectionTitle { font-size: 15px; font-weight: 600; }
                QLabel#badge { padding: 5px 9px; font-size: 11px; }
                QLabel#configurationName { font-size: 13px; }
                QPushButton[nav="true"] { text-align: left; padding: 7px 8px; }
                QPushButton[nav="true"]:checked {
                    background: palette(highlight); color: palette(highlighted-text); }
                QFrame#topbar { border-bottom: 2px solid palette(shadow); }
                QFrame#launchbar { border-top: 2px solid palette(shadow); }
                QFrame#playTile { background: palette(base);
                    border: 2px solid palette(shadow); }
                QLabel#playTitle { font-size: 21px; font-weight: 700; }
                QLabel#playSubtitle { font-size: 12px; }
                QPushButton#playButton { font-size: 17px; font-weight: 700;
                    padding: 10px 28px; }
                QToolButton { padding: 8px; }
                QPushButton#launchButton { font-weight: 700; padding: 10px 24px; }
                QSplitter::handle { background: palette(window); }
                QSplitter::handle:hover { background: palette(highlight); }
                QScrollArea { border: 0; background: palette(window); }
            """


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
        self.netplay_page = None
        self._restore_library_after_quick = False
        self.widget().setObjectName("dashboard")
        self.set_min_size((1000, 720))
        self.restyle()
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

        self.content_stack = QStackedWidget()
        self.workspace = QWidget()
        workspace_layout = QVBoxLayout(self.workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(12)
        self.content_stack.addWidget(self.workspace)
        body_layout.addWidget(self.content_stack, 1)

        self.play_tile = PlayTile(owner)
        self.play_tile.edit_button.toggled.connect(self._toggle_editor)
        workspace_layout.addWidget(self.play_tile)

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
        workspace_layout.addWidget(self.splitter, 1)
        self.play_tile.edit_button.setChecked(PlayTile.editor_visible_setting())
        self.editor.setVisible(self.play_tile.edit_button.isChecked())

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
        workspace_layout.addWidget(self.media)
        self.launch_bar = self._launchbar()
        body_layout.addWidget(self.launch_bar)
        status = owner.status_bar.widget()
        status.setFixedHeight(30)
        body_layout.addWidget(status)
        status.show()
        body_layout.setSpacing(12)
        LauncherSettings.add_listener(self)
        theme_applied.connect(self.restyle)
        owner.closed.connect(self._remove_listener)
        self.on_setting("config_name", LauncherSettings.get("config_name"))
        self._show_page(0)

    def restyle(self):
        """Re-render theme colours; called again after a live theme change."""
        if fsui.theme_variant == "modern":
            self.widget().setStyleSheet(modern_theme.render(MODERN_STYLESHEET))
        else:
            self.widget().setStyleSheet(PALETTE_STYLESHEET)
        if hasattr(self, "nav_buttons"):
            for button, (_, icon) in zip(self.nav_buttons, self.PAGES):
                button.setIcon(self._icon(icon))
            self.netplay_button.setIcon(self._icon(QStyle.SP_DriveNetIcon))
            for button, icon in self._extra_icons:
                button.setIcon(self._icon(icon))
            self.library_toggle.setIcon(self._icon(QStyle.SP_FileDialogContentsView))
            self.quick_toggle.setIcon(self._icon(QStyle.SP_FileDialogDetailedView))
            for button in self.launch_host.widget().findChildren(QPushButton):
                if button.objectName() == "launchButton":
                    button.setIcon(
                        navigation_icon("fa5s.play", on_accent=True)
                        if fsui.theme_variant == "modern"
                        else self._icon(QStyle.SP_MediaPlay)
                    )
            self.play_tile.restyle_icons()

    def _toggle_editor(self, checked):
        self.editor.setVisible(checked)
        PlayTile.remember_editor_visible(checked)

    def on_theme_changed(self):
        """Re-measure the scrolled panels after a font change."""
        for panel in (self.owner.books[1], self.owner.books[2]):
            widget = panel.widget()
            widget.setMinimumSize(
                max(280, panel.get_min_width()), max(100, panel.get_min_height())
            )
        quick_area = getattr(self, "quick_area", None)
        if quick_area is not None and quick_area.widget() is not None:
            panel = self.owner.quick_settings_panel
            quick_area.widget().setMinimumSize(
                max(280, panel.get_min_width()), max(100, panel.get_min_height())
            )

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
        return navigation_icon(names[standard_icon])

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
        self._extra_icons = []
        icon_size = QSize(24, 24) if fsui.theme_variant in (
            "windows311", "workbench"
        ) else QSize(20, 20)
        for index, (title, icon) in enumerate(self.PAGES):
            button = QPushButton(
                self._icon(icon), gettext(title).replace("&", "&&")
            )
            button.setProperty("nav", True)
            button.setCheckable(True)
            button.setMinimumHeight(44)
            button.setIconSize(icon_size)
            button.setToolTip(gettext(title))
            self.nav_group.addButton(button, index)
            layout.addWidget(button)
            self.nav_buttons.append(button)
        self.nav_group.idClicked.connect(self._show_page)
        self.nav_buttons[0].setChecked(True)
        layout.addStretch(1)
        self.netplay_button = QPushButton(
            self._icon(QStyle.SP_DriveNetIcon), gettext("Net play")
        )
        self.netplay_button.setProperty("nav", True)
        self.netplay_button.setCheckable(True)
        self.netplay_button.setMinimumHeight(42)
        self.netplay_button.setIconSize(icon_size)
        self.netplay_button.setToolTip(gettext("Net play"))
        self.nav_group.addButton(self.netplay_button, len(self.PAGES))
        layout.addWidget(self.netplay_button)
        for title, icon, callback in (
            ("Settings", QStyle.SP_FileDialogDetailedView,
             self.owner.on_settings_button),
            ("Tools & account", QStyle.SP_TitleBarMenuButton, self._tools),
        ):
            button = QPushButton(
                self._icon(icon), gettext(title).replace("&", "&&")
            )
            button.setProperty("nav", True)
            button.setMinimumHeight(42)
            button.setIconSize(icon_size)
            button.clicked.connect(callback)
            layout.addWidget(button)
            self._extra_icons.append((button, icon))
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
                button.setIcon(
                    navigation_icon("fa5s.play", on_accent=True)
                    if fsui.theme_variant == "modern"
                    else self._icon(QStyle.SP_MediaPlay)
                )
        layout.addWidget(self.launch_host.widget(), 1)
        self.launch_host.widget().show()
        return frame

    def _show_page(self, index):
        if index == len(self.PAGES):
            self.show_netplay()
            return
        self.content_stack.setCurrentWidget(self.workspace)
        self.library_toggle.setEnabled(True)
        self.quick_toggle.setEnabled(True)
        self.launch_bar.show()
        if index > 0 and not self.play_tile.edit_button.isChecked():
            # Choosing a configuration page implies wanting the editor.
            self.play_tile.edit_button.setChecked(True)
        self.owner.books[2].set_page(index)
        self.page_title.setText(gettext(self.PAGES[index][0]))
        self.nav_buttons[index].setChecked(True)
        width = self.owner.books[2].get_min_width()
        height = self.owner.books[2].get_min_height()
        self.owner.books[2].widget().setMinimumSize(width, height)

    def show_netplay(self):
        if self.netplay_page is None:
            from launcher.netplay.netplay_page import NetplayPage

            self.netplay_page = NetplayPage(self)
            self.content_stack.addWidget(self.netplay_page.widget())
        self.content_stack.setCurrentWidget(self.netplay_page.widget())
        self.netplay_button.setChecked(True)
        self.page_title.setText(gettext("Net play"))
        self.library_toggle.setEnabled(False)
        self.quick_toggle.setEnabled(False)
        self.launch_bar.hide()
        self.netplay_page.on_show()

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
        if self.netplay_page is not None:
            self.netplay_page.shutdown()
        self.play_tile.shutdown()
        theme_applied.disconnect(self.restyle)
        LauncherSettings.remove_listener(self)