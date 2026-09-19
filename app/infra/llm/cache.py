import hashlib
import sqlite3
import threading
from functools import lru_cache
from typing import Optional, Protocol

from app.core.config import get_settings


class CacheRepository(Protocol):
    def get(self, key: str) -> Optional[str]: ...

    def set(self, key: str, value: str) -> None: ...


class SqliteCacheRepository:
    def __init__(self, db_path: str):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("CREATE TABLE IF NOT EXISTS llm_cache (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self._conn.commit()

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            row = self._conn.execute("SELECT value FROM llm_cache WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO llm_cache (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            self._conn.commit()


def make_key(*parts) -> str:
    hasher = hashlib.sha256()
    for part in parts:
        hasher.update(str(part).encode("utf-8"))
        hasher.update(b"\x00")
    return hasher.hexdigest()


@lru_cache
def get_cache() -> CacheRepository:
    return SqliteCacheRepository(get_settings().qc_cache_db)
