import sqlite3

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class Database:
    def __init__(
        self,
        path: Path,
        timeout: float = 5.0,
    ) -> None:
        self.path = Path(path)
        self.timeout = timeout

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self.path,
            timeout=self.timeout,
        )

        connection.row_factory = sqlite3.Row

        try:
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
