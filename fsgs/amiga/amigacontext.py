import os
import logging
from threading import Thread

from fsbc.application import call_after
from fsbc.paths import Paths
from fsgs.archive import Archive
from fsgs.BaseContext import BaseContext
from fsgs.checksumtool import ChecksumTool
from fsgs.FSGSDirectories import FSGSDirectories
from fsgs.filedatabase import FileDatabase
from fsgs.amiga.amiga import Amiga

logger = logging.getLogger(__name__)


class AmigaContext(BaseContext):
    def __init__(self, main_context):
        BaseContext.__init__(self, main_context)
        self._cd_checksum_request = 0
        self.cd_checksums_pending = False

    def reset_all_floppies(self):
        for i in range(Amiga.MAX_FLOPPY_DRIVES):
            self.eject_floppy(i)
        self.clear_floppy_list()

    def eject_floppy(self, drive):
        values = [
            (f"floppy_drive_{drive}", ""),
            (f"x_floppy_drive_{drive}_sha1", ""),
        ]
        self.set_config(values)

    def clear_floppy_list(self):
        values = []
        for i in range(Amiga.MAX_FLOPPY_IMAGES):
            values.append((f"floppy_image_{i}", ""))
            values.append((f"x_floppy_image_{i}_sha1", ""))
        self.set_config(values)

    def insert_floppy_in_free_drive(self, path, sha1=None):
        for i in range(Amiga.MAX_FLOPPY_DRIVES):
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
        default_dir = FSGSDirectories.get_cdroms_dir()
        path = Paths.contract_path(path, default_dir)
        self.update_cd_checksums(
            [
                (f"cdrom_drive_{drive}", path),
                (f"x_cdrom_drive_{drive}_sha1", sha1 or ""),
            ]
        )

    def eject_cd(self, drive):
        self.set_config(
            [
                (f"cdrom_drive_{drive}", ""),
                (f"x_cdrom_drive_{drive}_sha1", ""),
            ]
        )
        self.update_cd_checksums()

    def insert_cd_images(self, paths):
        default_dir = FSGSDirectories.get_cdroms_dir()
        paths = [
            Paths.contract_path(path, default_dir)
            for path in paths[: Amiga.MAX_CDROM_IMAGES]
        ]
        values = [
            ("cdrom_drive_0", paths[0] if paths else ""),
            ("x_cdrom_drive_0_sha1", ""),
        ]
        for i in range(Amiga.MAX_CDROM_IMAGES):
            values.extend(
                [
                    (f"cdrom_image_{i}", paths[i] if i < len(paths) else ""),
                    (f"x_cdrom_image_{i}_sha1", ""),
                ]
            )
        self.update_cd_checksums(values)

    def update_cd_checksums(self, selection=None):
        self._cd_checksum_request += 1
        request = self._cd_checksum_request
        selection = list(selection or [])
        original = {key: self.config.get(key) for key, _ in selection}
        config = self.config.copy()
        config.update(selection)
        pending: list[tuple[str, str]] = []
        for kind, count in (
            ("drive", Amiga.MAX_CDROM_DRIVES),
            ("image", Amiga.MAX_CDROM_IMAGES),
        ):
            for i in range(count):
                key = f"cdrom_{kind}_{i}"
                path = config.get(key)
                if path and not config.get(f"x_{key}_sha1"):
                    pending.append((key, path))
        self.cd_checksums_pending = bool(pending)
        if not pending:
            if selection:
                self.set_config(selection)
            return

        def calculate():
            checksums: dict[str, str] = {}
            for _, path in pending:
                if path not in checksums:
                    try:
                        checksums[path] = self._checksum_cd(path)
                    except Exception:
                        logger.exception(
                            "Could not checksum CD image %r", path
                        )
                        checksums[path] = ""

            def apply():
                # A new insertion/load supersedes this job. Also check paths
                # so ejecting a CD while hashing cannot restore its checksum.
                if request != self._cd_checksum_request:
                    return
                self.cd_checksums_pending = False
                if any(
                    self.config.get(key) != value
                    for key, value in original.items()
                ):
                    return
                values = dict(selection)
                values.update(
                    [
                        (f"x_{key}_sha1", checksums[path])
                        for key, path in pending
                        if checksums[path]
                        and (
                            key in original
                            or (
                                self.config.get(key) == path
                                and not self.config.get(f"x_{key}_sha1")
                            )
                        )
                    ]
                )
                if values:
                    # Publish a selection and its hashes together, so a
                    # hosted game never sends an empty intermediate hash.
                    self.set_config(values.items())

            call_after(apply)

        Thread(target=calculate, name="cd-checksum", daemon=True).start()

    @staticmethod
    def _checksum_cd(path):
        if path.startswith(("http://", "https://")):
            return path
        resolved = Paths.expand_path(path)
        if not os.path.exists(resolved):
            resolved = os.path.join(FSGSDirectories.get_cdroms_dir(), resolved)
        archive_path = Archive(resolved).path
        stat = os.stat(archive_path)
        record = FileDatabase.get_instance().find_file(path=resolved)
        # Scanned metadata is reusable only while the file is unchanged.
        if (
            record["sha1"]
            and record["size"] == stat.st_size
            and record["mtime"] == int(stat.st_mtime)
        ):
            sha1 = record["sha1"].hex()
        else:
            sha1 = ChecksumTool().checksum(resolved)
            after = os.stat(archive_path)
            if (after.st_size, after.st_mtime_ns) != (
                stat.st_size,
                stat.st_mtime_ns,
            ):
                raise OSError(
                    "CD image changed while calculating its checksum"
                )
        # Netplay resolves media by SHA-1, including images not yet scanned.
        size = stat.st_size if archive_path == resolved else -1
        FileDatabase.add_static_file(resolved, size, sha1)
        return sha1

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
