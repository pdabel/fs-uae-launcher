import os

from fsgs.filedatabase import FileDatabase
from fsgs.util.gamenameutil import GameNameUtil
from .i18n import gettext


class ConfigurationScanner:
    def __init__(self, paths=None, on_status=None, stop_check=None):
        if paths is None:
            paths = []
        self.paths = paths
        self.on_status = on_status
        self._stop_check = stop_check
        self.scan_count = 0

    def stop_check(self):
        if self._stop_check:
            return self._stop_check()

    def set_status(self, title, status):
        if self.on_status:
            self.on_status((title, status))

    def scan_fs_uae_files(self, database):
        cursor = database.cursor()
        cursor.execute("SELECT id, path FROM game WHERE path IS NOT NULL")
        config_path_ids = {}
        for row in cursor:
            config_path_ids[database.decode_path(row[1])] = row[0]

        file_database = FileDatabase.get_instance()
        configurations = file_database.find_files(ext=".fs-uae")
        for c in configurations:
            if self.stop_check():
                break
            path = c["path"]
            name = os.path.basename(path)
            name, ext = os.path.splitext(name)
            sort_key = name.lower()
            name = self.create_configuration_name(name)

            game_id = database.add_configuration(
                path=path, name=name, sort_key=sort_key
            )
            database.update_game_search_terms(
                game_id, self.create_search_terms(name)
            )

            print(config_path_ids)
            try:
                del config_path_ids[path]
            except KeyError:
                pass

                # FIXME: try splitting name into name, variant pair, and
                # actually add game_variant for config files as well, where
                # possible

        for id in config_path_ids.values():
            database.delete_game(id=id)

    def scan(self, database):
        self.set_status(
            gettext("Scanning configurations"), gettext("Please wait...")
        )

        self.set_status(
            gettext("Scanning configurations"),
            gettext("Scanning .fs-uae files..."),
        )
        self.scan_fs_uae_files(database)

        if self.stop_check():
            return

    @staticmethod
    def delete_configuration(database, path):
        path = os.path.abspath(path)
        if not path.lower().endswith(".fs-uae"):
            raise ValueError("Only saved .fs-uae configuration files can be deleted.")
        file_database = FileDatabase.get_instance()
        with database, file_database:
            cursor = database.cursor()
            cursor.execute(
                "SELECT id, uuid FROM game WHERE path = ?",
                (database.encode_path(path),),
            )
            rows = cursor.fetchall()
            if not rows or any(row[1] for row in rows):
                raise ValueError("This item is not an indexed local configuration.")
            for game_id, _ in rows:
                database.delete_game(id=game_id)
            file_database.delete_file(path=path)
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass

    @classmethod
    def create_search_terms(cls, name):
        search_terms = set()
        game_name = name.split("(", 1)[0]
        search_terms.update(GameNameUtil.extract_index_terms(game_name))
        return search_terms

    @classmethod
    def create_configuration_name(cls, name):
        if "(" in name:
            primary, secondary = name.split("(", 1)
            secondary = secondary.replace(", ", " \u00b7 ")
            name = primary.rstrip() + "\n" + secondary.lstrip()
            if name[-1] == ")":
                name = name[:-1]
            name = name.replace(") (", " \u00b7 ")
            name = name.replace(")(", " \u00b7 ")
        return name
