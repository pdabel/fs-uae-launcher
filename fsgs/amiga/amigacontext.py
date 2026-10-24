import os

from fsbc.paths import Paths
from fsgs.archive import Archive
from fsgs.BaseContext import BaseContext
from fsgs.checksumtool import ChecksumTool
from fsgs.FSGSDirectories import FSGSDirectories
from fsgs.amiga.amiga import Amiga

class AmigaContext(BaseContext):
    def __init__(self, main_context):
        BaseContext.__init__(self, main_context)

    def reset_all_floppies(self):
        # FIXME: MAX_AMIGA_FLOPPY_DRIVES
        for i in range(4):
            self.eject_floppy(i)
        self.clear_floppy_list()

    def eject_floppy(self, drive):
        values = [
            (f"floppy_drive_{drive}", ""),
            (f"x_floppy_drive_{drive}_sha1", ""),
        ]
        self.set_config(values)

        # self.notify("fsgs:config:floppy_drive_{0}".format(drive), "")
        # self.notify("fsgs:config:x_floppy_drive_{0}_sha1".format(drive), "")

    def clear_floppy_list(self):
        values = []
        for i in range(Amiga.MAX_FLOPPY_IMAGES):
            values.append((f"floppy_image_{i}", ""))
            values.append((f"x_floppy_image_{i}_sha1", ""))
        self.set_config(values)

    def insert_floppy_in_free_drive(self, path, sha1=None):
        # FIXME: max floppy drives
        for i in range(4):
            if not self.config.get(f"floppy_drive_{i}"):
                self.insert_floppy(i, path, sha1=sha1)
                return True
        return False

    def insert_floppy(self, drive, path, sha1=None):
        if sha1 is None:
            sha1 = ChecksumTool().checksum(path)
        default_dir = FSGSDirectories.get_floppies_dir()
        path = Paths.contract_path(path, default_dir)
        self.set_config(
            [
                (f"floppy_drive_{drive}", path),
                (f"x_floppy_drive_{drive}_sha1", sha1),
            ]
        )

    def insert_cd(self, drive, path, sha1=None):
        if sha1 is None:
            sha1 = ""
            print("FIXME: not calculating CD checksum just yet")
        default_dir = FSGSDirectories.get_cdroms_dir()
        path = Paths.contract_path(path, default_dir)
        self.set_config(
            [
                (f"cdrom_drive_{drive}", path),
                (f"x_cdrom_drive_{drive}_sha1", sha1),
            ]
        )

    def insert_multiple_floppies(self, insert_paths):
        paths = []
        for path in insert_paths:
            embedded_files = []
            if path.endswith(".zip"):
                archive = Archive(path)
                files = archive.list_files()
                for file in files:
                    name, ext = os.path.splitext(file)
                    # FIXME: get list of floppy extensions from a central
                    # place
                    if ext in [".adf", ".ipf"]:
                        embedded_files.append(file)
            if len(embedded_files) > 0:
                embedded_files.sort()
                print("found embedded floppy images:")
                print(embedded_files)
                for file in embedded_files:
                    paths.append(file)
            else:
                paths.append(path)

        default_dir = FSGSDirectories.get_floppies_dir()
        checksum_tool = ChecksumTool()
        for i, path in enumerate(paths):
            sha1 = checksum_tool.checksum(path)
            path = Paths.contract_path(path, default_dir)

            if i < 4:
                self.set_config(
                    [
                        (f"floppy_drive_{i}", path),
                        (f"x_floppy_drive_{i}_sha1", sha1),
                    ]
                )
            self.set_config(
                [
                    (f"floppy_image_{i}", path),
                    (f"x_floppy_image_{i}_sha1", sha1),
                ]
            )

        # blank the rest of the drives
        for i in range(len(paths), 4):
            self.set_config(
                [
                    (f"floppy_drive_{i}", ""),
                    (f"x_floppy_drive_{i}_sha1", ""),
                ]
            )
        # blank the rest of the image list
        for i in range(len(paths), 20):
            self.set_config(
                [
                    (f"floppy_image_{i}", ""),
                    (f"x_floppy_image_{i}_sha1", ""),
                ]
            )

    def get_base_dir(self):
        # FIXME: dependency loop
        return FSGSDirectories.get_base_dir()

    def get_floppies_dir(self):
        # FIXME: dependency loop
        return FSGSDirectories.get_floppies_dir()

    def get_cdroms_dir(self):
        # FIXME: dependency loop
        return FSGSDirectories.get_cdroms_dir()

    def get_hard_drives_dir(self):
        # FIXME: dependency loop
        return FSGSDirectories.get_hard_drives_dir()

    def get_kickstarts_dir(self):
        # FIXME: dependency loop
        return FSGSDirectories.get_kickstarts_dir()

    def get_controllers_dir(self):
        # FIXME: dependency loop
        return FSGSDirectories.get_controllers_dir()
