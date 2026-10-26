import traceback
from launcher.ui.ConfigGroup import ConfigGroup
from fsgs.context import fsgs
from fsgs.Database import Database
import fsui
from ..launcher_config import LauncherConfig
from ..launcher_signal import LauncherSignal
from ..launcher_settings import LauncherSettings


class LastVariants(object):
    def __init__(self):
        self.cache = {}
        LauncherSignal.add_listener("quit", self)

    def on_quit_signal(self):
        database = Database.get_instance()
        for key, value in self.cache.items():
            database.set_last_game_variant(key, value)
        database.commit()


class VariantsBrowser(fsui.ItemChoice):
    @staticmethod
    def use_horizontal_layout():
        return False

    def __init__(self, parent):
        fsui.ItemChoice.__init__(self, parent)

        self.parent_uuid = ""
        self.items = []  # type: list [dict]

        self.icon = fsui.Image("launcher:res/fsuae_config_16.png")
        self.adf_icon = fsui.Image("launcher:res/adf_game_16.png")
        self.ipf_icon = fsui.Image("launcher:res/ipf_game_16.png")
        self.cd_icon = fsui.Image("launcher:res/cd_game_16.png")
        self.hd_icon = fsui.Image("launcher:res/hd_game_16.png")
        self.missing_icon = fsui.Image("launcher:res/16x16/delete_grey.png")
        self.missing_color = fsui.Color(0xA8, 0xA8, 0xA8)

        self.blank_icon = fsui.Image("launcher:res/16x16/blank.png")
        self.bullet_icon = fsui.Image("launcher:res/16x16/bullet.png")

        self.manual_download_icon = fsui.Image(
            "launcher:res/16x16/arrow_down_yellow.png"
        )
        self.auto_download_icon = fsui.Image(
            "launcher:res/16x16/arrow_down_green.png"
        )

        self.up_icon = fsui.Image("launcher:res/16x16/thumb_up_mod.png")
        self.down_icon = fsui.Image("launcher:res/16x16/thumb_down_mod.png")
        self.fav_icon = fsui.Image("launcher:res/rating_fav_16.png")

        LauncherSettings.add_listener(self)
        self.on_setting("parent_uuid", LauncherSettings.get("parent_uuid"))

    def on_destroy(self):
        LauncherSettings.remove_listener(self)

    def on_select_item(self, index):
        if index is None:
            return
        self.load_variant(self.items[index])

    # noinspection PyMethodMayBeStatic
    def on_activate_item(self, _):
        from ..launcherapp import LauncherApp

        LauncherApp.start_game()

    def on_setting(self, key, value):
        if key == "parent_uuid":
            self.parent_uuid = value
            if value:
                self.update_list(value)
            else:
                LauncherSettings.set("game_uuid", "")
                self.set_items([])
                self.disable()
        elif key == "__variant_rating":
            variant_uuid = LauncherConfig.get("variant_uuid")
            for item in self.items:
                if item["uuid"] == variant_uuid:
                    item["personal_rating"] = int(value or 0)
                    self.update()
                    break

    def set_items(self, items):
        self.items = items
        self.update()

    def get_item_count(self):
        return len(self.items)

    def get_item_text(self, index):
        name = self.items[index]["name"]
        name = name.replace(", ", " \u00b7 ")
        return name

    def get_item_text_color(self, index):
        have = self.items[index]["have"]
        if not have:
            return self.missing_color

    NOT_AVAILABLE = 0
    MANUAL_AVAILABLE = 1
    AUTO_AVAILABLE = 2
    AVAILABLE = 3

    def get_item_icon(self, index):
        have = self.items[index]["have"]
        if have == self.NOT_AVAILABLE:
            return self.blank_icon
        if have == self.MANUAL_AVAILABLE:
            return self.manual_download_icon
        if have == self.AUTO_AVAILABLE:
            return self.auto_download_icon
        return self.get_item_extra_icons(index)[0] or self.bullet_icon

    def get_item_extra_icons(self, index):
        personal_rating = self.items[index]["personal_rating"]
        if personal_rating == 5:
            return [self.fav_icon]
        elif personal_rating == 4:
            return [self.up_icon]
        elif personal_rating == 3:
            return [self.up_icon]
        elif personal_rating == 2:
            return [self.down_icon]
        elif personal_rating == 1:
            return [self.down_icon]
        return [None]

    def update_list(self, game_uuid):
        print("VariantsBrowser.update_list, game_uuid=", game_uuid)
        database = Database.get_instance()
        items = database.find_game_variants_new(game_uuid, have=0)

        # FIXME: Merge code with
        # FSGameSystemContext.py:get_ordered_game_variants
        sortable_items = []
        for i, variant in enumerate(items):
            name = variant["name"]

            game_database = fsgs.game_database(variant["database"])
            variant["like_rating"], variant[
                "work_rating"
            ] = game_database.get_ratings_for_game(variant["uuid"])
            variant[
                "personal_rating"
            ], ignored = database.get_ratings_for_game(variant["uuid"])

            if variant["published"] == 0:
                primary_sort = 1
                variant["name"] = "[UNPUBLISHED] " + variant["name"]
            else:
                primary_sort = 0
            sort_key = (
                primary_sort,
                1000000 - variant["like_rating"],
                1000000 - variant["work_rating"],
                name,
            )
            sortable_items.append((sort_key, i, variant))
        self.items = [x[2] for x in sorted(sortable_items)]
        self.update()

        self.select_item(None, signal=False)

        select_index = None
        list_uuid = LauncherSettings.get("game_list_uuid")
        if list_uuid:
            list_variant_uuid = database.get_variant_for_list_and_game(
                list_uuid, game_uuid
            )
            print(
                "game list", list_uuid, "override variant", list_variant_uuid
            )
        else:
            list_variant_uuid = None
        if list_variant_uuid:
            # override variant selection from list if possible
            for i, variant in enumerate(self.items):
                print(variant["uuid"], variant["name"], list_variant_uuid)
                if variant["uuid"] == list_variant_uuid:
                    select_index = i
                    print("override select index", select_index)
                    break
        if select_index is None:
            # default index selection
            for i, variant in enumerate(self.items):
                if variant["personal_rating"] == 5:
                    if variant["have"] >= 3:
                        select_index = i
                        break
                    else:
                        # FIXME: Add warning here that the favorite variant
                        # could not be selected.
                        pass
            else:
                for i, variant in enumerate(self.items):
                    if variant["have"] >= 3:
                        select_index = i
                        break
                else:
                    for i, variant in enumerate(self.items):
                        if variant["have"] >= 1:
                            select_index = i
                            break
                    else:
                        if len(self.items) > 0:
                            select_index = 0

        self.enable(len(self.items) > 0)
        if select_index is not None:
            print("selecting variant index", select_index)
            self.select_item(select_index)
        else:
            ConfigGroup.new_config()

    def load_variant(self, item):
        try:
            self._load_variant(item)
        except Exception:
            traceback.print_exc()
            LauncherConfig.load_default_config()
            LauncherConfig.load({"__error": "Error Loading Configuration"})
            self.select_item(None)

    def _load_variant(self, item):
        print("_load_variant", item)
        variant_uuid = item["uuid"]
        database_name = item["database"]
        personal_rating = item["personal_rating"]
        have = item["have"]
        self._load_variant_2(
            variant_uuid, database_name, personal_rating, have
        )

    def _load_variant_2(
        self, variant_uuid, database_name, personal_rating, have
    ):
        if LauncherConfig.get("variant_uuid") == variant_uuid:
            print(f"Variant {variant_uuid} is already loaded")
        game_database = fsgs.game_database(database_name)

        try:
            values = game_database.get_game_values_for_uuid(variant_uuid)
        except Exception:
            # game not found:
            traceback.print_exc()
            print("could not find game", repr(variant_uuid))
            LauncherConfig.load_default_config()
            return

        LauncherConfig.load_values(values, uuid=variant_uuid)

        LauncherConfig.set("__changed", "0")
        LauncherConfig.set("__database", database_name)

        LauncherSettings.set("__variant_rating", str(personal_rating))

        if int(have) < self.AVAILABLE:
            print(" -- some files are missing --")
            LauncherConfig.set("x_missing_files", "1")

    def get_min_width(self):
        return 0
