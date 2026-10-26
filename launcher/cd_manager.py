from fsbc.paths import Paths
from fsgs.FSGSDirectories import FSGSDirectories
from fsgs.amiga.amiga import Amiga
from launcher.i18n import gettext
from launcher.launcher_config import LauncherConfig
from launcher.ui.LauncherFilePicker import LauncherFilePicker


class CDManager:
    @classmethod
    def clear_all(cls):
        for i in range(1):
            cls.eject(i)
        cls.clear_cdrom_list()

    @classmethod
    def eject(cls, drive):
        values = [
            (f"cdrom_drive_{drive}", ""),
            (f"x_cdrom_drive_{drive}_sha1", ""),
        ]
        LauncherConfig.set_multiple(values)

    @classmethod
    def clear_cdrom_list(cls):
        values = []
        for i in range(Amiga.MAX_CDROM_IMAGES):
            values.append((f"cdrom_image_{i}", ""))
            values.append((f"x_cdrom_image_{i}_sha1", ""))
        LauncherConfig.set_multiple(values)

    @classmethod
    def multi_select(cls, parent=None):
        default_dir = FSGSDirectories.get_cdroms_dir()
        dialog = LauncherFilePicker(
            parent, gettext("Select Multiple CD-ROMs"), "cd", multiple=True
        )

        if not dialog.show_modal():
            return
        paths = dialog.get_paths()
        paths.sort()

        for i, path in enumerate(paths):
            sha1 = ""
            print("FIXME: not calculating CD checksum just yet")
            path = Paths.contract_path(path, default_dir)

            if i < 1:
                LauncherConfig.set_multiple(
                    [
                        (f"cdrom_drive_{i}", path),
                        (f"x_cdrom_drive_{i}_sha1", sha1),
                    ]
                )
            LauncherConfig.set_multiple(
                [
                    (f"cdrom_image_{i}", path),
                    (f"x_cdrom_image_{i}_sha1", sha1),
                ]
            )

        # blank the rest of the drives
        for i in range(len(paths), 1):
            LauncherConfig.set_multiple(
                [
                    (f"cdrom_drive_{i}", ""),
                    (f"x_cdrom_drive_{i}_sha1", ""),
                ]
            )

        # blank the rest of the image list
        for i in range(len(paths), Amiga.MAX_CDROM_IMAGES):
            LauncherConfig.set_multiple(
                [
                    (f"cdrom_image_{i}", ""),
                    (f"x_cdrom_image_{i}_sha1", ""),
                ]
            )
