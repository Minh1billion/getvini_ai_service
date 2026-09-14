import hashlib
import os
import sqlite3
import threading

_DB_PATH = os.environ.get(
    "QC_CACHE_DB",
    os.path.join(os.path.dirname(__file__), "qc_cache.sqlite3"),
)

_lock = threading.Lock()
_conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
_conn.execute(
    "CREATE TABLE IF NOT EXISTS llm_cache (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
)
_conn.commit()


def make_key(*parts) -> str:
    hasher = hashlib.sha256()
    for part in parts:
        hasher.update(str(part).encode("utf-8"))
        hasher.update(b"\x00")
    return hasher.hexdigest()


def get(key: str):
    with _lock:
        row = _conn.execute(
            "SELECT value FROM llm_cache WHERE key = ?", (key,)
        ).fetchone()
    return row[0] if row else None


def set(key: str, value: str):
    with _lock:
        _conn.execute(
            "INSERT INTO llm_cache (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        _conn.commit()