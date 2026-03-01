import json
import logging
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ScheduledTask:
    id: str
    name: str
    schedule_type: str
    schedule_value: str
    action_type: str
    action_payload: str  # raw JSON string
    next_run: Optional[str]
    last_run: Optional[str]
    last_result: Optional[str]
    status: str
    created_at: str


class SchedulerDB:
    def __init__(self, db_path: str):
        dir_name = os.path.dirname(db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self):
        with self._lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    id             TEXT PRIMARY KEY,
                    name           TEXT NOT NULL,
                    schedule_type  TEXT NOT NULL
                                   CHECK(schedule_type IN ('cron', 'interval', 'once')),
                    schedule_value TEXT NOT NULL,
                    action_type    TEXT NOT NULL
                                   CHECK(action_type IN ('plugin', 'speak')),
                    action_payload TEXT NOT NULL,
                    next_run       TEXT,
                    last_run       TEXT,
                    last_result    TEXT,
                    status         TEXT NOT NULL DEFAULT 'active'
                                   CHECK(status IN ('active', 'paused', 'completed')),
                    created_at     TEXT NOT NULL
                )
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_status_next_run
                ON scheduled_tasks (status, next_run)
            """)
            self._conn.commit()

    def add_task(
        self,
        name: str,
        schedule_type: str,
        schedule_value: str,
        action_type: str,
        action_payload: dict,
        next_run: str,
    ) -> str:
        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO scheduled_tasks
                    (id, name, schedule_type, schedule_value, action_type,
                     action_payload, next_run, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)
                """,
                (
                    task_id, name, schedule_type, schedule_value,
                    action_type, json.dumps(action_payload), next_run, now,
                ),
            )
            self._conn.commit()
        return task_id

    def get_due_tasks(self) -> list:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM scheduled_tasks WHERE status = 'active' AND next_run <= ?",
                (now,),
            ).fetchall()
        return [self._row_to_task(r) for r in rows]

    def update_after_run(
        self,
        task_id: str,
        result: str,
        next_run: Optional[str],
        status: str,
    ):
        now = datetime.now(timezone.utc).isoformat()
        truncated = (result or "")[:500]
        with self._lock:
            if next_run is None:
                self._conn.execute(
                    """
                    UPDATE scheduled_tasks
                    SET last_run = ?, last_result = ?, next_run = NULL, status = ?
                    WHERE id = ?
                    """,
                    (now, truncated, status, task_id),
                )
            else:
                self._conn.execute(
                    """
                    UPDATE scheduled_tasks
                    SET last_run = ?, last_result = ?, next_run = ?, status = ?
                    WHERE id = ?
                    """,
                    (now, truncated, next_run, status, task_id),
                )
            self._conn.commit()

    def set_status(self, task_id: str, status: str):
        with self._lock:
            self._conn.execute(
                "UPDATE scheduled_tasks SET status = ? WHERE id = ?",
                (status, task_id),
            )
            self._conn.commit()

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM scheduled_tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return self._row_to_task(row) if row else None

    def _row_to_task(self, row) -> ScheduledTask:
        return ScheduledTask(
            id=row["id"],
            name=row["name"],
            schedule_type=row["schedule_type"],
            schedule_value=row["schedule_value"],
            action_type=row["action_type"],
            action_payload=row["action_payload"],
            next_run=row["next_run"],
            last_run=row["last_run"],
            last_result=row["last_result"],
            status=row["status"],
            created_at=row["created_at"],
        )

    def close(self):
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
