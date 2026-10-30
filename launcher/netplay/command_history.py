import os
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from fsgs.FSGSDirectories import FSGSDirectories


class CommandHistory:
    limit = 100
    safe_commands = {
        "reset",
        "recheck",
        "resetconfig",
        "joingame",
        "set",
        "hostgame",
        "startgame",
        "startserver",
        "join",
        "leave",
        "part",
        "whois",
        "back",
    }

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None
        self.entries = []
        self.position = None
        self.draft = ""

    @contextmanager
    def connect(self):
        path = self.path
        if path is None:
            path = (
                Path(FSGSDirectories.databases_dir()) / "NetplayHistory.sqlite"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(
                path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("PRAGMA secure_delete=ON")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS command_history ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "command TEXT NOT NULL UNIQUE)"
            )
            yield connection

    @classmethod
    def can_store(cls, text):
        if not text.startswith("/") or "\n" in text or "\r" in text:
            return False
        parts = text[1:].split(" ")
        command = parts[0].lower()
        if command not in cls.safe_commands:
            return False
        if command in {"hostgame", "startgame", "startserver"}:
            return len(parts) <= 3
        if command == "joingame":
            return len(parts) == 3
        if command == "join":
            return len(parts) <= 2
        if command == "set":
            key = parts[1].lower() if len(parts) > 1 else ""
            return not any(
                word in key
                for word in (
                    "pass",
                    "token",
                    "secret",
                    "auth",
                    "key",
                    "credential",
                )
            )
        return True

    def add(self, text):
        text = text.strip()
        self.reset()
        if not self.can_store(text):
            return
        with self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO command_history (command) VALUES (?)",
                (text,),
            )
            connection.execute(
                "DELETE FROM command_history WHERE id NOT IN "
                "(SELECT id FROM command_history ORDER BY id DESC LIMIT ?)",
                (self.limit,),
            )

    def previous(self, draft):
        if self.position is None:
            with self.connect() as connection:
                self.entries = [
                    row[0]
                    for row in connection.execute(
                        "SELECT command FROM command_history ORDER BY id"
                    )
                ]
            if not self.entries:
                return draft
            self.draft = draft
            self.position = len(self.entries)
        self.position = max(0, self.position - 1)
        return self.entries[self.position]

    def next(self, current):
        if self.position is None:
            return current
        self.position += 1
        if self.position >= len(self.entries):
            draft = self.draft
            self.reset()
            return draft
        return self.entries[self.position]

    def reset(self):
        self.entries = []
        self.position = None
        self.draft = ""

    def clear(self):
        with self.connect() as connection:
            connection.execute("DELETE FROM command_history")
        self.reset()
