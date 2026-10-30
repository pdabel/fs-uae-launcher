import os
import sqlite3
import time

import qtawesome as qta
from qtpy.QtCore import QEvent, QRect, Qt
from qtpy.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QToolTip

from fsgs.Database import Database
from fsgs.platform import PlatformHandler
from fsgs.util.gamenameutil import GameNameUtil
import fsui
from ..launcher_config import LauncherConfig
from ..launcher_settings import LauncherSettings
from launcher.configuration_scanner import ConfigurationScanner
from launcher.i18n import gettext


class ConfigurationItemDelegate(QStyledItemDelegate):
    @staticmethod
    def delete_rect(rect):
        return QRect(rect.right() - 31, rect.top(), 32, rect.height())

    def paint(self, painter, option, index):
        browser = self.parent()
        if not browser.can_delete_configuration(index.row()):
            super().paint(painter, option, index)
            return
        style = browser.style()
        style.drawPrimitive(QStyle.PE_PanelItemViewItem, option, painter, browser)
        text_option = QStyleOptionViewItem(option)
        text_option.rect.adjust(0, 0, -32, 0)
        super().paint(painter, text_option, index)
        selected = bool(option.state & QStyle.State_Selected)
        color = option.palette.highlightedText().color() if selected else option.palette.text().color()
        icon = qta.icon("fa5s.trash-alt", color=color.name())
        rect = self.delete_rect(option.rect)
        icon_rect = QRect(0, 0, 16, 16)
        icon_rect.moveCenter(rect.center())
        icon.paint(painter, icon_rect)


class ConfigurationsBrowser(fsui.VerticalItemView):
    def __init__(self, parent):
        fsui.VerticalItemView.__init__(self, parent)
        self.items = []
        self.game_icon = fsui.Image("launcher:res/16x16/controller.png")
        self.config_icon = fsui.Image("launcher:res/fsuae_config_16.png")
        LauncherSettings.add_listener(self)
        self.update_search()

        self.manual_download_icon = fsui.Image(
            "launcher:res/16x16/arrow_down_yellow.png"
        )
        self.auto_download_icon = fsui.Image(
            "launcher:res/16x16/arrow_down_green.png"
        )
        self.blank_icon = fsui.Image("launcher:res/16x16/blank.png")
        self.missing_color = fsui.Color(0xA8, 0xA8, 0xA8)
        self.unpublished_color = fsui.Color(0xCC, 0x00, 0x00)

        self.platform_icons = {}
        self._delete_pressed = None
        self.setItemDelegate(ConfigurationItemDelegate(self))

    def can_delete_configuration(self, index):
        if index is None or not 0 <= index < len(self.items):
            return False
        item = self.items[index]
        return not item["uuid"] and bool(item["path"]) and item["path"].lower().endswith(".fs-uae")

    def delete_index_at(self, position):
        index = self.indexAt(position)
        if index.isValid() and self.can_delete_configuration(index.row()):
            rect = ConfigurationItemDelegate.delete_rect(self.visualRect(index))
            if rect.contains(position):
                return index.row()
        return None

    def mousePressEvent(self, event):
        index = self.delete_index_at(event.position().toPoint())
        if event.button() == Qt.LeftButton and index is not None:
            self._delete_pressed = self.items[index]["path"]
            event.accept()
            return
        self._delete_pressed = None
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        pressed = self._delete_pressed
        self._delete_pressed = None
        index = self.delete_index_at(event.position().toPoint())
        if event.button() == Qt.LeftButton and pressed is not None:
            if index is not None and self.items[index]["path"] == pressed:
                self.delete_configuration(index)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.delete_index_at(event.position().toPoint()) is not None:
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def viewportEvent(self, event):
        if event.type() == QEvent.ToolTip and self.delete_index_at(event.pos()) is not None:
            QToolTip.showText(event.globalPos(), gettext("Delete Configuration"), self.viewport())
            return True
        return super().viewportEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete and event.modifiers() == Qt.NoModifier:
            index = self.get_index()
            if self.can_delete_configuration(index):
                self.delete_configuration(index)
            event.accept()
            return
        super().keyPressEvent(event)

    def delete_configuration(self, index):
        from fsui.qt import QMessageBox
        from fsui.qt.helpers import QParent
        from launcher.scanner import Scanner

        if not self.can_delete_configuration(index):
            return
        if Scanner.running:
            fsui.show_error(gettext("Wait for the database scan to finish before deleting a configuration."), gettext("Delete Configuration"), parent=self)
            return
        item = self.items[index]
        database = Database.get_instance()
        path = database.decode_path(item["path"])
        answer = QMessageBox.question(
            QParent(self), gettext("Delete Configuration"),
            gettext(
                "Permanently delete this configuration file?\n\n{path}\n\n"
                "Game disks, ROMs, and save data will not be deleted. "
                "If this configuration is open, its unsaved changes will also be discarded."
            ).format(path=path),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        if Scanner.running:
            fsui.show_error(gettext("Wait for the database scan to finish before deleting a configuration."), gettext("Delete Configuration"), parent=self)
            return
        try:
            ConfigurationScanner.delete_configuration(database, path)
        except (OSError, sqlite3.Error, ValueError) as error:
            fsui.show_error(str(error), gettext("Unable to delete configuration"), parent=self)
            return
        active_path = LauncherSettings.get("config_path")
        if active_path and os.path.normcase(os.path.abspath(active_path)) == os.path.normcase(os.path.abspath(path)):
            LauncherConfig.load_default_config()
            LauncherSettings.set("parent_uuid", "")
        LauncherSettings.set("__config_deleted", str(time.time_ns()))

    def on_destroy(self):
        LauncherSettings.remove_listener(self)

    def on_select_item(self, index):
        if index is None:
            return
        self.load_configuration(self.items[index])

    def on_activate_item(self, index):
        from ..launcherapp import LauncherApp

        LauncherApp.start_game()

    def on_setting(self, key, _):
        if key in [
            "config_search",
            "game_list_uuid",
            "database_show_games",
            "database_show_adult",
            "database_show_unpublished",
        ]:
            self.update_search()
            if len(self.items) > 0:
                self.select_item(None)
                self.select_item(0)
            else:
                if LauncherSettings.get("parent_uuid"):
                    LauncherSettings.set("parent_uuid", "")
                    LauncherConfig.load_default_config()
        elif key == "__config_deleted":
            index = self.get_index()
            selected = self.items[index] if index is not None and 0 <= index < len(self.items) else None
            self.update_search()
            if selected is not None:
                for index, item in enumerate(self.items):
                    if item["uuid"] == selected["uuid"] and item["path"] == selected["path"]:
                        selection = self.selectionModel()
                        blocked = selection.blockSignals(True)
                        try:
                            self.select_item(index)
                        finally:
                            selection.blockSignals(blocked)
                        break
        elif key == "__config_refresh":
            self.update_search()
            self.select_item(None)
            old_parent_uuid = LauncherSettings.get("parent_uuid")
            if old_parent_uuid:
                LauncherSettings.set("parent_uuid", "")
                LauncherSettings.set("parent_uuid", old_parent_uuid)
        elif key == "parent_uuid" or key == "config_path":
            if not (
                LauncherSettings.get("parent_uuid")
                or LauncherSettings.get("config_path")
            ):
                self.select_item(None)

    def set_items(self, items):
        self.model.beginResetModel()
        self.items = items
        self.model.endResetModel()
        self.update()

    def get_item_count(self):
        return len(self.items)

    def get_item_text(self, index):
        item = self.items[index]
        name = item[str("name")]
        platform = item[str("platform")] or ""
        if "[" in name:
            name, extra = name.split("[", 1)
            name = name.strip()
            extra = " \u00b7 " + extra.strip(" ]")
        else:
            extra = ""
        if fsui.toolkit == "wx":
            sep = "\n"
        else:
            sep = " \u00b7 "
            name = name.replace("\n", " \u00b7 ")
        if platform == "Amiga":
            platform = ""
        elif platform:
            platform = sep + PlatformHandler.get_platform_name(platform)
        text = f"{name}{extra}{platform}" or "Missing Name"
        return text

    def get_item_search_text(self, index):
        # FIXME: lower-case search string?
        return self.items[index][str("sort_key")]

    def get_item_text_color(self, index):
        have = self.items[index][str("have")]
        if not have:
            return self.missing_color
        published = self.items[index]["published"]
        if not published:
            return self.unpublished_color

    def get_item_icon(self, index):
        item = self.items[index]
        platform_id = (item[str("platform")] or "").lower()
        if item[str("have")] == 1:
            return self.manual_download_icon
        elif item[str("have")] == 0:
            return self.blank_icon
        elif item[str("have")] == 2:
            return self.auto_download_icon
        elif item[str("have")] == 4:
            if platform_id not in self.platform_icons:
                try:
                    icon = fsui.Image(
                        f"launcher:res/16x16/{platform_id}.png"
                    )
                except Exception:
                    icon = self.game_icon
                self.platform_icons[platform_id] = icon
            return self.platform_icons[platform_id]
        else:
            return self.config_icon

    def update_search(self):
        search = LauncherSettings.get("config_search").strip().lower()
        print("search for", search)
        words = []
        special = []
        for word in search.split(" "):
            word = word.strip()
            if not word:
                continue
            if ":" in word[1:-1]:
                special.append(word)
            else:
                words.append(word)
        terms = GameNameUtil.extract_search_terms(" ".join(words))
        terms.update(special)

        database = Database.get_instance()

        try:
            have = int(LauncherSettings.get("database_show_games"))
        except ValueError:
            # default is show all downloadable and locally available games
            have = 1
        items = database.find_games_new(
            " ".join(terms),
            have=have,
            list_uuid=LauncherSettings.get("game_list_uuid"),
        )

        self.set_items(items)

    # noinspection PyMethodMayBeStatic
    def load_configuration(self, item):
        if item[str("uuid")]:
            LauncherSettings.set("parent_uuid", item[str("uuid")])
        else:
            config_path = Database.get_instance().decode_path(
                item[str("path")]
            )
            print("load config from", config_path)
            LauncherConfig.load_file(config_path)
            LauncherSettings.set("parent_uuid", "")
