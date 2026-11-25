from fsgs.amiga.amiga import Amiga
from fsgs.context import fsgs
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
        fsgs.amiga.eject_cd(drive)

    @classmethod
    def clear_cdrom_list(cls):
        values = []
        for i in range(Amiga.MAX_CDROM_IMAGES):
            values.append((f"cdrom_image_{i}", ""))
            values.append((f"x_cdrom_image_{i}_sha1", ""))
        LauncherConfig.set_multiple(values)
        fsgs.amiga.update_cd_checksums()

    @classmethod
    def multi_select(cls, parent=None):
        dialog = LauncherFilePicker(
            parent, gettext("Select Multiple CD-ROMs"), "cd", multiple=True
        )

        if not dialog.show_modal():
            return
        paths = dialog.get_paths()
        paths.sort()
        fsgs.amiga.insert_cd_images(paths)
