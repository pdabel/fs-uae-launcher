import os
import shutil
import sqlite3
import tempfile
from configparser import ConfigParser
from contextlib import closing
from io import StringIO
from pathlib import Path


def write_atomic(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class PortableModeChange:
    def __init__(self, source, destination, marker, enabled, normal_path):
        self.source = Path(source).resolve()
        self.destination = Path(destination).resolve()
        self.marker = Path(marker)
        self.enabled = enabled
        self.normal_path = Path(normal_path)

    def validate(self):
        if not self.source.is_dir():
            raise OSError("The current data folder is no longer available.")
        if self.enabled and self.destination == self.source:
            raise OSError(
                "Choose a new empty folder so the original data can be kept unchanged."
            )
        if self.destination != self.source:
            if (
                self.source in self.destination.parents
                or self.destination in self.source.parents
            ):
                raise OSError(
                    "Choose a folder outside the current data folder."
                )
            if self.destination.exists() and (
                not self.destination.is_dir()
                or any(self.destination.iterdir())
            ):
                raise OSError(
                    "Choose an empty folder. Existing files will not be overwritten."
                )
        if not self.enabled and not self.marker.is_file():
            raise OSError("The portable startup file is no longer available.")
        folders = [self.marker.parent]
        if not self.enabled:
            folders.append(self.normal_path.parent)
            for parent in self.marker.parent.parents:
                if (parent / "Portable.ini").exists():
                    raise OSError(
                        "Another portable installation exists in a parent folder."
                    )
        destination_parent = self.destination.parent
        while not destination_parent.exists():
            destination_parent = destination_parent.parent
        folders.append(destination_parent)
        for folder in folders:
            folder.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=folder):
                pass

    def apply(self, progress=lambda message: None):
        self.validate()
        copied = self.destination != self.source
        created = not self.destination.exists()
        previous_normal = (
            self.normal_path.read_bytes()
            if not self.enabled and self.normal_path.exists()
            else None
        )
        normal_written = False
        try:
            if copied:
                shutil.copytree(
                    self.source,
                    self.destination,
                    dirs_exist_ok=True,
                    symlinks=True,
                    copy_function=lambda source, target: self.copy_file(
                        source, target, progress
                    ),
                )
                self.rebase_directories()
                self.rebase_preferences()
                self.rebase_configurations()
            if self.enabled:
                config = ConfigParser(interpolation=None)
                if self.marker.exists():
                    config.read(self.marker, encoding="UTF-8")
                if not config.has_section("launcher"):
                    config.add_section("launcher")
                config.set(
                    "launcher",
                    "base_dir",
                    os.path.relpath(self.destination, self.marker.parent),
                )
                content = StringIO()
                config.write(content)
                write_atomic(self.marker, content.getvalue().encode("UTF-8"))
            else:
                write_atomic(
                    self.normal_path, str(self.destination).encode("UTF-8")
                )
                normal_written = True
                descriptor, backup = tempfile.mkstemp(
                    prefix="Portable.ini.disabled-", dir=self.marker.parent
                )
                os.close(descriptor)
                try:
                    os.replace(self.marker, backup)
                except OSError:
                    os.unlink(backup)
                    raise
        except Exception:
            if normal_written:
                if previous_normal is None:
                    self.normal_path.unlink()
                else:
                    write_atomic(self.normal_path, previous_normal)
            if copied and self.destination.exists():
                shutil.rmtree(self.destination)
                if not created:
                    self.destination.mkdir()
            raise

    def copy_file(self, source, target, progress):
        progress(str(source))
        path = Path(source)
        if path.suffix == ".sqlite" and path.parent.name == "Databases":
            source_uri = path.resolve().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(source_uri, uri=True)) as original:
                with closing(sqlite3.connect(target)) as backup:
                    original.backup(backup)
                    backup.execute("PRAGMA journal_mode=DELETE")
        elif not (
            path.parent.name == "Databases"
            and path.name.endswith(
                (".sqlite-wal", ".sqlite-shm", ".sqlite-journal")
            )
        ):
            shutil.copy2(source, target)
        return target

    def rebase_preferences(self):
        portable = ConfigParser(interpolation=None)
        portable.read(self.destination / "Portable.ini", encoding="UTF-8")
        data_dir = portable.get("directories", "data_dir", fallback="Data")
        settings = self.destination / data_dir / "Settings.ini"
        if not settings.is_file() or not settings.resolve().is_relative_to(
            self.destination
        ):
            return
        config = ConfigParser(interpolation=None)
        config.optionxform = str
        config.read(settings, encoding="UTF-8")
        if config.has_section("settings"):
            source = str(self.source)
            destination = str(self.destination)
            for key, value in config.items("settings"):
                if key == "search_path":
                    paths = []
                    for entry in value.split(";"):
                        prefix = "-" if entry.startswith("-") else ""
                        path = entry[len(prefix) :]
                        if path == source or path.startswith(source + os.sep):
                            suffix = path[len(source) :].lstrip(os.sep)
                            path = (
                                "$BASE/" + suffix
                                if self.enabled
                                else destination + path[len(source) :]
                            )
                        paths.append(prefix + path)
                    config.set("settings", key, ";".join(paths))
                elif (
                    self.enabled
                    and key.startswith("last_")
                    and value.startswith(source + os.sep)
                ):
                    config.set("settings", key, "")
                elif value == source or value.startswith(source + os.sep):
                    config.set(
                        "settings", key, destination + value[len(source) :]
                    )
            for key in ("configurations_dir_mtime", "kickstarts_dir_mtime"):
                config.set("settings", key, "")
        with settings.open("w", encoding="UTF-8") as stream:
            config.write(stream)

    def rebase_configurations(self):
        source = str(self.source)
        for path in self.destination.rglob("*.fs-uae"):
            if not path.resolve().is_relative_to(self.destination):
                continue
            config = ConfigParser(interpolation=None)
            config.read(path, encoding="UTF-8")
            changed = False
            for section in config.sections():
                for key, value in config.items(section):
                    if value == source or value.startswith(source + os.sep):
                        suffix = value[len(source) :].lstrip(os.sep)
                        config.set(section, key, "$BASE/" + suffix)
                        changed = True
            if changed:
                with path.open("w", encoding="UTF-8") as stream:
                    config.write(stream)

    def rebase_directories(self):
        marker = self.destination / "Portable.ini"
        if not marker.is_file() or not marker.resolve().is_relative_to(
            self.destination
        ):
            return
        config = ConfigParser(interpolation=None)
        config.read(marker, encoding="UTF-8")
        changed = False
        if config.has_section("directories"):
            for key, value in config.items("directories"):
                path = Path(value)
                if path == self.source or self.source in path.parents:
                    config.set(
                        "directories", key, str(path.relative_to(self.source))
                    )
                    changed = True
        if changed:
            with marker.open("w", encoding="UTF-8") as stream:
                config.write(stream)
