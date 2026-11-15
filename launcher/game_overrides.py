import os
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from fsgs.FSGSDirectories import FSGSDirectories


class GameOverrideStore:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None

    @contextmanager
    def connect(self):
        path = self.path
        if path is None:
            path = (
                Path(FSGSDirectories.databases_dir())
                / "GameOverrides.sqlite"
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
            connection.execute(
                "CREATE TABLE IF NOT EXISTS game_config_override ("
                "identity_type TEXT NOT NULL, "
                "identity TEXT NOT NULL, "
                "key TEXT NOT NULL, "
                "value TEXT NOT NULL, "
                "PRIMARY KEY (identity_type, identity, key))"
            )
            yield connection

    def get(self, identity):
        if identity is None:
            return {}
        identity_type, identity_value = identity
        with self.connect() as connection:
            return dict(
                connection.execute(
                    "SELECT key, value FROM game_config_override "
                    "WHERE identity_type = ? AND identity = ?",
                    (identity_type, identity_value),
                )
            )

    def set(self, identity, key, value):
        if identity is None:
            raise ValueError("A stable game identity is required")
        identity_type, identity_value = identity
        with self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO game_config_override "
                "(identity_type, identity, key, value) VALUES (?, ?, ?, ?)",
                (identity_type, identity_value, key, str(value)),
            )

    def clear(self, identity, key):
        if identity is None:
            raise ValueError("A stable game identity is required")
        identity_type, identity_value = identity
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM game_config_override "
                "WHERE identity_type = ? AND identity = ? AND key = ?",
                (identity_type, identity_value, key),
            )


game_override_store = GameOverrideStore()
