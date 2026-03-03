import json
import logging
import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    key: str
    value: str          # JSON string
    updated_at: str     # ISO 8601 UTC
    ttl_s: int
    max_stale_s: int


class VoiceCache:
    """SQLite-backed cache for plugin responses.

    Stores small text/JSON payloads keyed by a plugin-defined string.
    Thread-safe. Multiple connections to the same file are safe because
    cache writes are infrequent (scheduled every few hours).
    """

    def __init__(self, db_path: str):
        dir_name = os.path.dirname(db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False, timeout=5)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self):
        with self._lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_entries (
                    key         TEXT PRIMARY KEY,
                    value       TEXT NOT NULL,
                    updated_at  TEXT NOT NULL,
                    ttl_s       INTEGER NOT NULL,
                    max_stale_s INTEGER NOT NULL
                )
            """)
            self._conn.commit()

    def get(self, key: str) -> Optional[CacheEntry]:
        """Return the cache entry for key, or None if not found."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM cache_entries WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        return CacheEntry(
            key=row["key"],
            value=row["value"],
            updated_at=row["updated_at"],
            ttl_s=row["ttl_s"],
            max_stale_s=row["max_stale_s"],
        )

    def set(self, key: str, value: str, ttl_s: int, max_stale_s: int):
        """Insert or update a cache entry."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO cache_entries (key, value, updated_at, ttl_s, max_stale_s)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value       = excluded.value,
                    updated_at  = excluded.updated_at,
                    ttl_s       = excluded.ttl_s,
                    max_stale_s = excluded.max_stale_s
                """,
                (key, value, now, ttl_s, max_stale_s),
            )
            self._conn.commit()
        logger.debug("Cache set: key=%r age=0s ttl=%ds", key, ttl_s)

    def age_s(self, entry: CacheEntry) -> float:
        """Return the age of an entry in seconds."""
        updated = datetime.fromisoformat(entry.updated_at)
        return (datetime.now(timezone.utc) - updated).total_seconds()

    def is_fresh(self, entry: CacheEntry) -> bool:
        """True if the entry is within its TTL."""
        return self.age_s(entry) <= entry.ttl_s

    def can_serve(self, entry: CacheEntry) -> bool:
        """True if the entry can be served (within max_stale)."""
        return self.age_s(entry) <= entry.max_stale_s

    def close(self):
        with self._lock:
            self._conn.close()
