from fsbc.task import Task
from fsgs.Database import Database
from fsgs.filedatabase import FileDatabase
from fsgs.LockerDatabase import LockerDatabase
from fsgs.context import fsgs
from launcher.i18n import gettext


class DefragmentDatabasesTask(Task):
    def __init__(self):
        Task.__init__(self, gettext("Defragment Databases"))

    def run(self):
        self.defragment(FileDatabase.get_instance(), "Files.sqlite")
        self.stop_check()
        self.defragment(LockerDatabase.instance(), "Locker.sqlite")
        self.stop_check()
        self.defragment(fsgs.get_game_database(), "Amiga.sqlite")
        self.stop_check()
        self.defragment(Database.get_instance(), "Database.sqlite")

    def defragment(self, database, name):
        self.set_progress(gettext("Defragmenting {name}").format(name=name))
        with database:
            cursor = database.cursor()
            cursor.execute("VACUUM")
