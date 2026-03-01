import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from common.db import SchedulerDB, ScheduledTask

logger = logging.getLogger(__name__)


class _PermanentTaskError(Exception):
    """Raised for unrecoverable task configuration errors (bad JSON, unknown action type)."""


def calc_next_run(schedule_type: str, schedule_value: str) -> Optional[str]:
    """Return the next ISO 8601 UTC run time, or None for once tasks."""
    now = datetime.now(timezone.utc)
    if schedule_type == "interval":
        interval_s = int(schedule_value)
        if interval_s < 1:
            raise ValueError(f"Interval must be >= 1 second, got {interval_s}")
        return (now + timedelta(seconds=interval_s)).isoformat()
    if schedule_type == "cron":
        from croniter import croniter
        return croniter(schedule_value, now).get_next(datetime).isoformat()
    if schedule_type == "once":
        return None
    raise ValueError(f"Unknown schedule_type: {schedule_type!r}")


class TaskScheduler:
    """
    Lightweight in-process task scheduler backed by SQLite.

    Supports three schedule types: 'cron', 'interval', 'once'.
    Supports two action types: 'speak' (TTS) and 'plugin' (invoke plugin).

    Usage::

        scheduler = TaskScheduler(db, speak_fn=..., invoke_plugin_fn=...)
        scheduler.start()

        task_id = scheduler.add_task(
            name="morning-weather",
            schedule_type="cron",
            schedule_value="0 9 * * *",
            action_type="plugin",
            action_payload={"plugin": "weather", "query": "weather", "refresh_only": False},
        )

        scheduler.stop()
    """

    def __init__(
        self,
        db: SchedulerDB,
        speak_fn: Callable[[str], None],
        invoke_plugin_fn: Callable[[str, str, bool], Optional[str]],
        poll_interval_s: int = 30,
    ):
        self._db = db
        self._speak_fn = speak_fn
        self._invoke_plugin_fn = invoke_plugin_fn
        self._poll_interval = poll_interval_s
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._loop, name="sandvoice-scheduler", daemon=True
        )

    # ── lifecycle ──────────────────────────────────────────────────────────

    def start(self):
        if self._thread.is_alive():
            return
        self._thread.start()
        logger.info("Task scheduler started (poll_interval=%ds)", self._poll_interval)

    def stop(self, timeout: Optional[float] = None):
        """Signal the scheduler to stop and wait for the worker thread to exit."""
        self._stop_event.set()
        if self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning(
                    "Scheduler thread did not exit within %s seconds", timeout
                )

    def close(self, timeout: Optional[float] = 5.0):
        """Stop the scheduler thread and close the database connection."""
        self.stop(timeout=timeout)
        self._db.close()

    # ── public API ─────────────────────────────────────────────────────────

    def add_task(
        self,
        name: str,
        schedule_type: str,
        schedule_value: str,
        action_type: str,
        action_payload: dict,
    ) -> str:
        if action_type == "speak" and "text" not in action_payload:
            raise ValueError("'speak' action requires 'text' in action_payload")
        if action_type == "plugin" and "plugin" not in action_payload:
            raise ValueError("'plugin' action requires 'plugin' in action_payload")
        first_run = self._first_run(schedule_type, schedule_value)
        task_id = self._db.add_task(
            name=name,
            schedule_type=schedule_type,
            schedule_value=schedule_value,
            action_type=action_type,
            action_payload=action_payload,
            next_run=first_run,
        )
        logger.info("Task registered: '%s' (%s) next_run=%s", name, task_id, first_run)
        return task_id

    def pause_task(self, task_id: str):
        self._db.set_status(task_id, "paused")
        logger.info("Task paused: %s", task_id)

    def resume_task(self, task_id: str):
        self._db.set_status(task_id, "active")
        logger.info("Task resumed: %s", task_id)

    def cancel_task(self, task_id: str):
        self._db.set_status(task_id, "completed")
        logger.info("Task cancelled: %s", task_id)

    # ── internals ──────────────────────────────────────────────────────────

    def _first_run(self, schedule_type: str, schedule_value: str) -> str:
        if schedule_type == "once":
            # Validate and normalize to UTC ISO string so TEXT comparison is reliable.
            try:
                dt = datetime.fromisoformat(schedule_value)
            except ValueError as e:
                raise ValueError(
                    f"Invalid ISO timestamp for 'once' schedule: {schedule_value!r}"
                ) from e
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt.isoformat()
        return calc_next_run(schedule_type, schedule_value)

    def _loop(self):
        while not self._stop_event.wait(self._poll_interval):
            self._tick()

    def _tick(self):
        try:
            due = self._db.get_due_tasks()
        except Exception as e:
            logger.error("Scheduler: error fetching due tasks: %s", e)
            return
        for task in due:
            if self._stop_event.is_set():
                break
            self._run(task)

    def _run(self, task: ScheduledTask):
        logger.debug("Running task '%s' (%s)", task.name, task.id)
        result = ""
        permanent_error = False
        try:
            result = self._dispatch(task) or ""
        except _PermanentTaskError as e:
            logger.error("Task '%s' has a permanent configuration error: %s", task.name, e)
            result = str(e)
            permanent_error = True
        except Exception as e:
            logger.error("Task '%s' failed: %s", task.name, e)
            result = str(e)

        if permanent_error:
            next_run = None
            status = "completed"
        else:
            try:
                next_run = calc_next_run(task.schedule_type, task.schedule_value)
                status = "completed" if next_run is None else "active"
            except Exception as e:
                logger.error("Scheduler: failed to compute next run for task '%s': %s", task.id, e)
                error_msg = f"schedule error: {e}"
                result = f"{result}\n{error_msg}" if result else error_msg
                next_run = None
                status = "completed"
        try:
            self._db.update_after_run(task.id, result, next_run, status)
        except Exception as e:
            logger.error("Scheduler: failed to update task '%s' after run: %s", task.id, e)

    def _dispatch(self, task: ScheduledTask) -> str:
        try:
            payload = json.loads(task.action_payload)
        except json.JSONDecodeError as e:
            raise _PermanentTaskError(f"malformed action_payload JSON: {e}") from e
        if task.action_type == "speak":
            text = payload.get("text", "")
            self._speak_fn(text)
            return f"spoke: {text[:80]}"
        if task.action_type == "plugin":
            plugin_name = payload.get("plugin", "")
            query = payload.get("query", "")
            refresh_only = bool(payload.get("refresh_only", False))
            result = self._invoke_plugin_fn(plugin_name, query, refresh_only)
            return result or ""
        raise _PermanentTaskError(f"Unknown action_type: {task.action_type!r}")
