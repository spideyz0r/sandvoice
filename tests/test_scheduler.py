import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from common.db import SchedulerDB
from common.scheduler import TaskScheduler, calc_next_run


# ── calc_next_run ──────────────────────────────────────────────────────────────

class TestCalcNextRun(unittest.TestCase):
    def test_interval_adds_seconds(self):
        before = datetime.now(timezone.utc)
        result = calc_next_run("interval", "300")
        after = datetime.now(timezone.utc)
        parsed = datetime.fromisoformat(result)
        self.assertGreaterEqual(parsed, before + timedelta(seconds=299))
        self.assertLessEqual(parsed, after + timedelta(seconds=301))

    def test_cron_returns_future(self):
        result = calc_next_run("cron", "*/2 * * * *")
        parsed = datetime.fromisoformat(result)
        self.assertGreaterEqual(parsed, datetime.now(timezone.utc))

    def test_once_returns_none(self):
        self.assertIsNone(calc_next_run("once", "2099-01-01T00:00:00"))

    def test_invalid_type_raises(self):
        with self.assertRaises(ValueError):
            calc_next_run("bogus", "123")


# ── SchedulerDB ────────────────────────────────────────────────────────────────

class TestSchedulerDB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        self.db = SchedulerDB(self.db_path)

    def tearDown(self):
        self.db.close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _future(self, seconds=60):
        return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()

    def _past(self, seconds=60):
        return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()

    def test_add_and_get_task(self):
        task_id = self.db.add_task(
            name="test", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "hello"},
            next_run=self._future(),
        )
        task = self.db.get_task(task_id)
        self.assertIsNotNone(task)
        self.assertEqual(task.name, "test")
        self.assertEqual(task.status, "active")
        self.assertEqual(json.loads(task.action_payload), {"text": "hello"})

    def test_get_due_tasks_returns_past(self):
        self.db.add_task(
            name="due", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "hi"},
            next_run=self._past(),
        )
        self.db.add_task(
            name="not-due", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "hi"},
            next_run=self._future(),
        )
        due = self.db.get_due_tasks()
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0].name, "due")

    def test_paused_task_not_returned(self):
        task_id = self.db.add_task(
            name="paused", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "hi"},
            next_run=self._past(),
        )
        self.db.set_status(task_id, "paused")
        self.assertEqual(self.db.get_due_tasks(), [])

    def test_update_after_run_sets_completed_for_once(self):
        task_id = self.db.add_task(
            name="one-shot", schedule_type="once", schedule_value="2099-01-01T00:00:00",
            action_type="speak", action_payload={"text": "bye"},
            next_run=self._past(),
        )
        self.db.update_after_run(task_id, "done", next_run=None, status="completed")
        task = self.db.get_task(task_id)
        self.assertEqual(task.status, "completed")
        self.assertEqual(task.last_result, "done")

    def test_update_after_run_keeps_active_for_interval(self):
        task_id = self.db.add_task(
            name="recurring", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "tick"},
            next_run=self._past(),
        )
        self.db.update_after_run(task_id, "ok", next_run=self._future(), status="active")
        task = self.db.get_task(task_id)
        self.assertEqual(task.status, "active")

    def test_set_status_pause_resume(self):
        task_id = self.db.add_task(
            name="t", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={}, next_run=self._future(),
        )
        self.db.set_status(task_id, "paused")
        self.assertEqual(self.db.get_task(task_id).status, "paused")
        self.db.set_status(task_id, "active")
        self.assertEqual(self.db.get_task(task_id).status, "active")

    def test_get_all_tasks_returns_every_row(self):
        self.db.add_task(
            name="t1", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "hello"}, next_run=self._future(),
        )
        self.db.add_task(
            name="t2", schedule_type="interval", schedule_value="120",
            action_type="speak", action_payload={"text": "world"}, next_run=self._future(),
        )
        tasks = self.db.get_all_tasks()
        self.assertEqual({"t1", "t2"}, {task.name for task in tasks})

    def test_delete_task_removes_row(self):
        task_id = self.db.add_task(
            name="delete-me", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "bye"}, next_run=self._future(),
        )
        self.db.delete_task(task_id)
        self.assertIsNone(self.db.get_task(task_id))

    def test_long_result_truncated_to_500(self):
        task_id = self.db.add_task(
            name="t", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={}, next_run=self._past(),
        )
        self.db.update_after_run(task_id, "x" * 600, next_run=self._future(), status="active")
        task = self.db.get_task(task_id)
        self.assertLessEqual(len(task.last_result), 500)


# ── TaskScheduler ──────────────────────────────────────────────────────────────

class TestTaskScheduler(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = SchedulerDB(os.path.join(self.tmp, "test.db"))
        self.speak_fn = MagicMock()
        self.invoke_fn = MagicMock(return_value="plugin result")
        self.scheduler = TaskScheduler(
            db=self.db,
            speak_fn=self.speak_fn,
            invoke_plugin_fn=self.invoke_fn,
            poll_interval_s=60,  # long so the loop doesn't auto-tick in tests
        )

    def tearDown(self):
        self.scheduler.stop()
        self.db.close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _past(self, seconds=60):
        return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()

    def _future(self, seconds=60):
        return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()

    def test_add_task_persists(self):
        task_id = self.scheduler.add_task(
            name="t", schedule_type="interval", schedule_value="300",
            action_type="speak", action_payload={"text": "hello"},
        )
        task = self.db.get_task(task_id)
        self.assertIsNotNone(task)
        self.assertEqual(task.name, "t")

    def test_speak_action_calls_speak_fn(self):
        task_id = self.db.add_task(
            name="speak-task", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "hello world"},
            next_run=self._past(),
        )
        self.scheduler._tick()
        self.speak_fn.assert_called_once_with("hello world")

    def test_plugin_action_calls_invoke_fn(self):
        task_id = self.db.add_task(
            name="plugin-task", schedule_type="interval", schedule_value="60",
            action_type="plugin",
            action_payload={"plugin": "weather", "query": "weather", "refresh_only": True},
            next_run=self._past(),
        )
        self.scheduler._tick()
        self.invoke_fn.assert_called_once_with("weather", "weather", True)

    def test_once_task_completed_after_run(self):
        task_id = self.db.add_task(
            name="once-task", schedule_type="once",
            schedule_value="2099-01-01T00:00:00+00:00",
            action_type="speak", action_payload={"text": "done"},
            next_run=self._past(),
        )
        self.scheduler._tick()
        task = self.db.get_task(task_id)
        self.assertEqual(task.status, "completed")

    def test_interval_task_stays_active_after_run(self):
        task_id = self.db.add_task(
            name="recurring", schedule_type="interval", schedule_value="300",
            action_type="speak", action_payload={"text": "ping"},
            next_run=self._past(),
        )
        self.scheduler._tick()
        task = self.db.get_task(task_id)
        self.assertEqual(task.status, "active")

    def test_pause_prevents_execution(self):
        task_id = self.scheduler.add_task(
            name="t", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "hi"},
        )
        # manually set next_run to past and pause
        self.db.update_after_run(task_id, "", self._past(), "active")
        self.scheduler.pause_task(task_id)
        self.scheduler._tick()
        self.speak_fn.assert_not_called()

    def test_resume_allows_execution(self):
        task_id = self.db.add_task(
            name="t", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "hi"},
            next_run=self._past(),
        )
        self.db.set_status(task_id, "paused")
        self.scheduler.resume_task(task_id)
        self.scheduler._tick()
        self.speak_fn.assert_called_once()

    def test_cancel_prevents_execution(self):
        task_id = self.db.add_task(
            name="t", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "hi"},
            next_run=self._past(),
        )
        self.scheduler.cancel_task(task_id)
        self.scheduler._tick()
        self.speak_fn.assert_not_called()

    def test_stop_event_set_on_stop(self):
        self.assertFalse(self.scheduler._stop_event.is_set())
        self.scheduler.stop()
        self.assertTrue(self.scheduler._stop_event.is_set())

    def test_dispatch_error_does_not_crash_tick(self):
        self.speak_fn.side_effect = RuntimeError("boom")
        self.db.add_task(
            name="bad", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "hi"},
            next_run=self._past(),
        )
        # should not raise
        self.scheduler._tick()

    def test_unknown_action_type_recorded_as_error(self):
        task_id = self.db.add_task(
            name="bad-action", schedule_type="interval", schedule_value="60",
            action_type="speak",  # valid for insert
            action_payload={"text": "hi"},
            next_run=self._past(),
        )
        # Patch action_type on the fetched task to simulate unknown type
        original_get_due = self.db.get_due_tasks
        bad_task = self.db.get_task(task_id)
        object.__setattr__(bad_task, "action_type", "unknown")
        with patch.object(self.db, "get_due_tasks", return_value=[bad_task]):
            self.scheduler._tick()
        task = self.db.get_task(task_id)
        self.assertIn("Unknown action_type", task.last_result)

    def test_unknown_action_type_marked_completed(self):
        """Permanent config errors (unknown action_type) must not reschedule the task."""
        task_id = self.db.add_task(
            name="bad-action", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "hi"},
            next_run=self._past(),
        )
        bad_task = self.db.get_task(task_id)
        object.__setattr__(bad_task, "action_type", "unknown")
        with patch.object(self.db, "get_due_tasks", return_value=[bad_task]):
            self.scheduler._tick()
        task = self.db.get_task(task_id)
        self.assertEqual(task.status, "completed")

    def test_bad_json_payload_permanent_error(self):
        """Malformed action_payload JSON marks task completed rather than rescheduling."""
        task_id = self.db.add_task(
            name="bad-json", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "hi"},
            next_run=self._past(),
        )
        bad_task = self.db.get_task(task_id)
        object.__setattr__(bad_task, "action_payload", "{invalid json")
        with patch.object(self.db, "get_due_tasks", return_value=[bad_task]):
            self.scheduler._tick()
        task = self.db.get_task(task_id)
        self.assertEqual(task.status, "completed")

    def test_start_idempotent(self):
        """Calling start() twice must not raise."""
        self.scheduler.start()
        self.scheduler.start()  # should be a no-op
        self.assertTrue(self.scheduler._thread.is_alive())

    def test_restart_after_stop(self):
        """start() after stop() must work without RuntimeError (fresh thread)."""
        self.scheduler.start()
        self.scheduler.stop(timeout=2)
        self.scheduler.start()  # must not raise
        self.assertTrue(self.scheduler._thread.is_alive())

    def test_add_task_speak_missing_text_raises(self):
        """add_task() must reject a speak action with no 'text' key."""
        with self.assertRaises(ValueError):
            self.scheduler.add_task(
                name="bad", schedule_type="interval", schedule_value="60",
                action_type="speak", action_payload={},
            )

    def test_add_task_speak_empty_text_raises(self):
        """add_task() must reject a speak action with empty 'text'."""
        with self.assertRaises(ValueError):
            self.scheduler.add_task(
                name="bad", schedule_type="interval", schedule_value="60",
                action_type="speak", action_payload={"text": "  "},
            )

    def test_add_task_plugin_missing_plugin_raises(self):
        """add_task() must reject a plugin action with no 'plugin' key."""
        with self.assertRaises(ValueError):
            self.scheduler.add_task(
                name="bad", schedule_type="interval", schedule_value="60",
                action_type="plugin", action_payload={"query": "weather"},
            )

    def test_add_task_unknown_action_type_raises(self):
        """add_task() must reject unknown action_type values."""
        with self.assertRaises(ValueError):
            self.scheduler.add_task(
                name="bad", schedule_type="interval", schedule_value="60",
                action_type="email", action_payload={},
            )

    def test_add_task_plugin_non_string_query_raises(self):
        """add_task() must reject a plugin action with non-string 'query'."""
        with self.assertRaises(ValueError):
            self.scheduler.add_task(
                name="bad", schedule_type="interval", schedule_value="60",
                action_type="plugin", action_payload={"plugin": "weather", "query": 42},
            )

    def test_add_task_plugin_invalid_refresh_only_type_raises(self):
        """add_task() must reject a plugin action with invalid 'refresh_only' type."""
        with self.assertRaises(ValueError):
            self.scheduler.add_task(
                name="bad", schedule_type="interval", schedule_value="60",
                action_type="plugin", action_payload={"plugin": "weather", "refresh_only": []},
            )

    def test_add_task_plugin_invalid_refresh_only_string_raises(self):
        """add_task() must reject a plugin action with an unrecognized 'refresh_only' string."""
        with self.assertRaises(ValueError):
            self.scheduler.add_task(
                name="bad", schedule_type="interval", schedule_value="60",
                action_type="plugin", action_payload={"plugin": "weather", "refresh_only": "maybe"},
            )

    def test_add_task_plugin_valid_optional_fields_accepted(self):
        """add_task() must accept valid optional plugin fields without raising."""
        task_id = self.scheduler.add_task(
            name="ok", schedule_type="interval", schedule_value="60",
            action_type="plugin",
            action_payload={"plugin": "weather", "query": "weather", "refresh_only": "true"},
        )
        self.assertIsNotNone(task_id)

    def test_add_task_plugin_whitespace_query_normalized(self):
        """add_task() must normalize whitespace-only 'query' to empty string in
        the persisted task, without mutating the caller's original dict."""
        payload = {"plugin": "weather", "query": "   "}
        task_id = self.scheduler.add_task(
            name="ws", schedule_type="interval", schedule_value="60",
            action_type="plugin", action_payload=payload,
        )
        # Caller's dict must NOT be mutated
        self.assertEqual(payload["query"], "   ")
        # Persisted JSON must have the normalized value
        task = self.db.get_task(task_id)
        self.assertEqual("", json.loads(task.action_payload).get("query"))

    def test_once_schedule_z_suffix_accepted(self):
        """add_task() must accept ISO timestamps with trailing Z for 'once' schedules."""
        task_id = self.scheduler.add_task(
            name="once-z", schedule_type="once",
            schedule_value="2099-06-01T12:00:00Z",
            action_type="speak", action_payload={"text": "hello"},
        )
        task = self.db.get_task(task_id)
        self.assertIsNotNone(task)
        # Should be stored as UTC ISO string (no trailing Z)
        self.assertIn("+00:00", task.next_run)

    def test_dispatch_plugin_non_string_query_permanent_error(self):
        """Plugin task with non-string 'query' is a permanent error."""
        task_id = self.db.add_task(
            name="bad-query", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "hi"},
            next_run=self._past(),
        )
        bad_task = self.db.get_task(task_id)
        object.__setattr__(bad_task, "action_type", "plugin")
        object.__setattr__(bad_task, "action_payload", '{"plugin": "weather", "query": 42}')
        with patch.object(self.db, "get_due_tasks", return_value=[bad_task]):
            self.scheduler._tick()
        task = self.db.get_task(task_id)
        self.assertEqual(task.status, "completed")

    def test_dispatch_plugin_invalid_refresh_only_permanent_error(self):
        """Plugin task with invalid 'refresh_only' type is a permanent error."""
        task_id = self.db.add_task(
            name="bad-refresh", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "hi"},
            next_run=self._past(),
        )
        bad_task = self.db.get_task(task_id)
        object.__setattr__(bad_task, "action_type", "plugin")
        object.__setattr__(bad_task, "action_payload", '{"plugin": "weather", "refresh_only": []}')
        with patch.object(self.db, "get_due_tasks", return_value=[bad_task]):
            self.scheduler._tick()
        task = self.db.get_task(task_id)
        self.assertEqual(task.status, "completed")

    def test_dispatch_plugin_string_refresh_only_true(self):
        """Plugin task with refresh_only='true' string resolves to True."""
        task_id = self.db.add_task(
            name="str-refresh", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "hi"},
            next_run=self._past(),
        )
        bad_task = self.db.get_task(task_id)
        object.__setattr__(bad_task, "action_type", "plugin")
        object.__setattr__(bad_task, "action_payload", '{"plugin": "weather", "refresh_only": "true"}')
        with patch.object(self.db, "get_due_tasks", return_value=[bad_task]):
            self.scheduler._tick()
        self.invoke_fn.assert_called_once_with("weather", "", True)

    def test_sync_tasks_registers_new_tasks_from_file(self):
        self.scheduler.sync_tasks([
            {
                "name": "morning-reminder",
                "schedule_type": "cron",
                "schedule_value": "0 9 * * *",
                "action_type": "speak",
                "action_payload": {"text": "hello"},
            }
        ])
        tasks = self.db.get_all_tasks()
        self.assertEqual(1, len(tasks))
        self.assertEqual({"morning-reminder"}, {task.name for task in tasks})

    def test_sync_tasks_deletes_db_tasks_missing_from_file(self):
        keep_id = self.db.add_task(
            name="keep", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "keep"}, next_run=self._future(),
        )
        remove_id = self.db.add_task(
            name="remove", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "remove"}, next_run=self._future(),
        )
        self.scheduler.sync_tasks([
            {
                "name": "keep",
                "schedule_type": "interval",
                "schedule_value": "60",
                "action_type": "speak",
                "action_payload": {"text": "keep"},
            }
        ])
        self.assertIsNotNone(self.db.get_task(keep_id))
        self.assertIsNone(self.db.get_task(remove_id))

    def test_sync_tasks_keeps_existing_db_task_unchanged(self):
        task_id = self.db.add_task(
            name="existing", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "original"}, next_run=self._future(),
        )
        original = self.db.get_task(task_id)
        self.scheduler.sync_tasks([
            {
                "name": "existing",
                "schedule_type": "interval",
                "schedule_value": "120",
                "action_type": "speak",
                "action_payload": {"text": "updated"},
            }
        ])
        task = self.db.get_task(task_id)
        self.assertEqual(original.schedule_value, task.schedule_value)
        self.assertEqual(json.loads(original.action_payload), json.loads(task.action_payload))

    def test_sync_tasks_empty_file_removes_all_db_tasks(self):
        task_id = self.db.add_task(
            name="old-task", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "old"}, next_run=self._future(),
        )
        self.scheduler.sync_tasks([])
        self.assertIsNone(self.db.get_task(task_id))

    def test_sync_tasks_invalid_entries_do_not_trigger_db_deletions(self):
        task_id = self.db.add_task(
            name="existing", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "keep"}, next_run=self._future(),
        )
        self.scheduler.sync_tasks(["oops"])
        self.assertIsNotNone(self.db.get_task(task_id))

    def test_sync_tasks_invalid_named_dict_entry_does_not_trigger_db_deletions(self):
        task_id = self.db.add_task(
            name="existing", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "keep"}, next_run=self._future(),
        )
        self.scheduler.sync_tasks([{
            "name": "broken-task",
            "action_type": "speak",
            "action_payload": {"text": "hello"},
        }])
        self.assertIsNotNone(self.db.get_task(task_id))

    def test_sync_tasks_invalid_schedule_does_not_trigger_db_deletions(self):
        task_id = self.db.add_task(
            name="existing", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "keep"}, next_run=self._future(),
        )
        self.scheduler.sync_tasks([{
            "name": "bad-schedule",
            "schedule_type": "interval",
            "schedule_value": "0",
            "action_type": "speak",
            "action_payload": {"text": "hello"},
        }])
        self.assertIsNotNone(self.db.get_task(task_id))

    def test_close_stops_scheduler_and_closes_db(self):
        """close() must stop the scheduler thread and close the DB without errors."""
        self.scheduler.start()
        self.scheduler.close(timeout=2)
        self.assertTrue(self.scheduler._stop_event.is_set())

    def test_dispatch_speak_missing_text_permanent_error(self):
        """speak tasks with missing/empty 'text' in payload are permanent errors."""
        task_id = self.db.add_task(
            name="no-text", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "hi"},
            next_run=self._past(),
        )
        bad_task = self.db.get_task(task_id)
        object.__setattr__(bad_task, "action_payload", '{"text": ""}')
        with patch.object(self.db, "get_due_tasks", return_value=[bad_task]):
            self.scheduler._tick()
        task = self.db.get_task(task_id)
        self.assertEqual(task.status, "completed")

    def test_dispatch_plugin_missing_plugin_permanent_error(self):
        """plugin tasks with missing/empty 'plugin' in payload are permanent errors."""
        task_id = self.db.add_task(
            name="no-plugin", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "hi"},
            next_run=self._past(),
        )
        bad_task = self.db.get_task(task_id)
        object.__setattr__(bad_task, "action_type", "plugin")
        object.__setattr__(bad_task, "action_payload", '{"query": "weather"}')
        with patch.object(self.db, "get_due_tasks", return_value=[bad_task]):
            self.scheduler._tick()
        task = self.db.get_task(task_id)
        self.assertEqual(task.status, "completed")

    def test_db_close_idempotent(self):
        """SchedulerDB.close() must be safe to call and sets conn to None."""
        from common.db import SchedulerDB
        import tempfile, os
        tmp = tempfile.mkdtemp()
        db = SchedulerDB(os.path.join(tmp, "t.db"))
        db.close()
        self.assertIsNone(db._conn)
        import shutil; shutil.rmtree(tmp, ignore_errors=True)

    def test_once_task_stays_active_on_transient_error(self):
        """Once tasks that fail with a transient error must remain active for retry."""
        task_id = self.db.add_task(
            name="once-fail", schedule_type="once",
            schedule_value="2099-01-01T00:00:00+00:00",
            action_type="speak", action_payload={"text": "hello"},
            next_run=self._past(),
        )
        # Make speak_fn raise a transient (non-permanent) error
        self.speak_fn.side_effect = RuntimeError("TTS service unavailable")
        self.scheduler._tick()
        task = self.db.get_task(task_id)
        self.assertEqual(task.status, "active",
                         "once task must stay active after transient error")
        self.assertIsNotNone(task.next_run)

    def test_set_status_invalid_raises_value_error(self):
        """set_status() must raise ValueError for unknown status strings."""
        future = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()
        task_id = self.db.add_task(
            name="t", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={}, next_run=future,
        )
        with self.assertRaises(ValueError):
            self.db.set_status(task_id, "unknown_status")


# ── TaskScheduler.get_active_or_paused_task_by_name ────────────────────────────

class TestSchedulerGetActiveOrPausedByName(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = SchedulerDB(os.path.join(self.tmp, "test.db"))
        self.scheduler = TaskScheduler(
            db=self.db,
            speak_fn=MagicMock(),
            invoke_plugin_fn=MagicMock(),
            poll_interval_s=60,
        )
        self.future = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()

    def tearDown(self):
        self.scheduler.stop()
        self.db.close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_returns_active_task(self):
        self.scheduler.add_task(
            name="cache_refresh:news:http://example.com/rss",
            schedule_type="interval", schedule_value="3600",
            action_type="plugin", action_payload={"plugin": "news", "query": "news"},
        )
        found = self.scheduler.get_active_or_paused_task_by_name(
            "cache_refresh:news:http://example.com/rss"
        )
        self.assertIsNotNone(found)

    def test_returns_none_for_unknown_name(self):
        self.assertIsNone(
            self.scheduler.get_active_or_paused_task_by_name("nonexistent")
        )


# ── SchedulerDB.get_active_or_paused_task_by_name ──────────────────────────────

class TestGetActiveOrPausedTaskByName(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = SchedulerDB(os.path.join(self.tmp, "test.db"))
        self.future = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()
        self.past = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()

    def tearDown(self):
        self.db.close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_returns_active_task(self):
        task_id = self.db.add_task(
            name="my-task", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "hi"}, next_run=self.future,
        )
        found = self.db.get_active_or_paused_task_by_name("my-task")
        self.assertIsNotNone(found)
        self.assertEqual(found.id, task_id)

    def test_returns_paused_task(self):
        task_id = self.db.add_task(
            name="paused-task", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "hi"}, next_run=self.future,
        )
        self.db.set_status(task_id, "paused")
        found = self.db.get_active_or_paused_task_by_name("paused-task")
        self.assertIsNotNone(found)

    def test_returns_none_for_completed_task(self):
        task_id = self.db.add_task(
            name="done-task", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "hi"}, next_run=self.past,
        )
        self.db.set_status(task_id, "completed")
        self.assertIsNone(self.db.get_active_or_paused_task_by_name("done-task"))

    def test_returns_none_when_no_match(self):
        self.assertIsNone(self.db.get_active_or_paused_task_by_name("nonexistent"))


# ── calc_next_run interval validation ──────────────────────────────────────────

class TestCalcNextRunIntervalValidation(unittest.TestCase):
    def test_zero_interval_raises(self):
        with self.assertRaises(ValueError):
            calc_next_run("interval", "0")

    def test_negative_interval_raises(self):
        with self.assertRaises(ValueError):
            calc_next_run("interval", "-10")

    def test_one_second_interval_ok(self):
        result = calc_next_run("interval", "1")
        self.assertIsNotNone(result)


# ── SchedulerDB compound index ─────────────────────────────────────────────────

class TestSchedulerDBIndex(unittest.TestCase):
    """Verify the compound index on (status, next_run) is created by _init_schema()."""

    def test_status_next_run_index_exists(self):
        import sqlite3
        tmp = tempfile.mkdtemp()
        try:
            db_path = os.path.join(tmp, "idx_test.db")
            db = SchedulerDB(db_path)
            db.close()
            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND tbl_name='scheduled_tasks'"
            ).fetchall()
            conn.close()
            index_names = [r[0] for r in rows]
            self.assertIn("idx_scheduled_tasks_status_next_run", index_names)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


# ── SandVoice scheduler init / route ──────────────────────────────────────────

class TestSandVoiceSchedulerInit(unittest.TestCase):
    """Tests for SandVoice._init_scheduler() error handling and _scheduler_route_message()."""

    def _make_stub(self, scheduler_enabled=True):
        from sandvoice import SandVoice
        sv = object.__new__(SandVoice)
        sv.config = MagicMock()
        sv.config.scheduler_enabled = scheduler_enabled
        sv.config.scheduler_db_path = ":memory:"
        sv.config.scheduler_poll_interval = 30
        sv.config.debug = False
        sv._scheduler_ai = None
        sv._ai_audio_lock = threading.Lock()
        sv._scheduler_audio = None
        sv.plugins = {}
        return sv

    def test_normalize_plugin_name_does_not_apply_route_aliases(self):
        """Plugin/module normalization must stay independent from route alias mapping."""
        from sandvoice import normalize_plugin_name

        self.assertEqual(normalize_plugin_name("default-rote"), "default_rote")

    def test_is_valid_plugin_module_name_accepts_python_identifiers(self):
        """Plugin module validation must match Python identifier rules."""
        from sandvoice import is_valid_plugin_module_name

        self.assertTrue(is_valid_plugin_module_name("hacker_news"))
        self.assertFalse(is_valid_plugin_module_name("hacker news"))
        self.assertFalse(is_valid_plugin_module_name("123plugin"))
        self.assertFalse(is_valid_plugin_module_name("plugin.name"))

    def test_suggested_plugin_module_name_returns_valid_identifier(self):
        """Invalid plugin filenames should get a valid Python module suggestion."""
        from sandvoice import suggested_plugin_module_name

        self.assertEqual(suggested_plugin_module_name("123plugin"), "_123plugin")
        self.assertEqual(suggested_plugin_module_name("plugin.name"), "plugin_name")
        self.assertEqual(suggested_plugin_module_name("hacker-news"), "hacker_news")
        self.assertEqual(suggested_plugin_module_name("123-plugin"), "_123_plugin")

    def test_init_scheduler_disabled_returns_none(self):
        sv = self._make_stub(scheduler_enabled=False)
        self.assertIsNone(sv._init_scheduler())

    def test_init_scheduler_db_failure_returns_none(self):
        """_init_scheduler must catch SchedulerDB init failures and return None."""
        sv = self._make_stub(scheduler_enabled=True)
        with patch("sandvoice.SchedulerDB", side_effect=OSError("permission denied")):
            result = sv._init_scheduler()
        self.assertIsNone(result)

    def test_scheduler_route_message_uses_scheduler_ai(self):
        """_scheduler_route_message must use _scheduler_ai for LLM fallback, not self.ai."""
        sv = self._make_stub()
        sv._scheduler_ai = MagicMock()
        sv._scheduler_ai.generate_response.return_value.content = "scheduler response"
        sv.ai = MagicMock()  # main AI instance — must NOT be called
        result = sv._scheduler_route_message("hello", {"route": "nonexistent"})
        sv._scheduler_ai.generate_response.assert_called_once_with("hello")
        sv.ai.generate_response.assert_not_called()
        self.assertEqual(result, "scheduler response")

    def test_scheduler_route_message_uses_plugin(self):
        """_scheduler_route_message must pass a _SchedulerContext proxy to plugins so
        plugin calls to ctx.ai use the scheduler AI, not the main self.ai."""
        sv = self._make_stub()
        sv._scheduler_ai = MagicMock()
        sv.ai = MagicMock()
        mock_plugin = MagicMock(return_value="plugin output")
        sv.plugins = {"weather": mock_plugin}
        result = sv._scheduler_route_message("weather now", {"route": "weather"})
        mock_plugin.assert_called_once()
        call_args = mock_plugin.call_args[0]
        self.assertEqual(call_args[0], "weather now")
        self.assertEqual(call_args[1], {"route": "weather"})
        # Third arg must be a proxy whose .ai is the scheduler AI (not self.ai)
        ctx = call_args[2]
        self.assertIs(ctx.ai, sv._scheduler_ai)
        sv._scheduler_ai.generate_response.assert_not_called()
        sv.ai.generate_response.assert_not_called()
        self.assertEqual(result, "plugin output")

    # ── load_plugins helpers ──────────────────────────────────────────────────

    @staticmethod
    def _make_file_entry(filename, base="/tmp/plugins"):
        """Return a mock DirEntry for a .py file (not a directory)."""
        entry = MagicMock()
        entry.name = filename
        entry.path = f"{base}/{filename}"
        entry.is_dir.return_value = False
        return entry

    @staticmethod
    def _make_scandir_mock(entries):
        """Return a mock for os.scandir that works as a context manager yielding entries."""
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=iter(entries))
        cm.__exit__ = MagicMock(return_value=False)
        return MagicMock(return_value=cm)

    # ── load_plugins tests ────────────────────────────────────────────────────

    def test_load_plugins_registers_hyphen_alias_for_underscore_module(self):
        """load_plugins() must register both canonical underscore and hyphen aliases."""
        from sandvoice import SandVoice

        sv = object.__new__(SandVoice)
        sv.config = MagicMock()
        sv.config.plugin_path = "/tmp/plugins"
        sv.plugins = {}

        module = MagicMock(spec=["process"])
        module.process = MagicMock()

        entries = [self._make_file_entry("hacker_news.py")]
        with patch("sandvoice.os.path.exists", return_value=True), \
             patch("sandvoice.os.scandir", self._make_scandir_mock(entries)), \
             patch("sandvoice.importlib.import_module", return_value=module):
            sv.load_plugins()

        self.assertIs(sv.plugins["hacker_news"], module.process)
        self.assertIs(sv.plugins["hacker-news"], module.process)

    def test_load_plugins_warns_and_skips_non_underscore_safe_filename(self):
        """load_plugins() must not import a normalized name different from the file on disk."""
        from sandvoice import SandVoice

        sv = object.__new__(SandVoice)
        sv.config = MagicMock()
        sv.config.plugin_path = "/tmp/plugins"
        sv.plugins = {}

        entries = [self._make_file_entry("hacker-news.py")]
        with patch("sandvoice.os.path.exists", return_value=True), \
             patch("sandvoice.os.scandir", self._make_scandir_mock(entries)), \
             patch("sandvoice.importlib.import_module") as import_module, \
             self.assertLogs("sandvoice", level="WARNING") as logs:
            sv.load_plugins()

        import_module.assert_not_called()
        self.assertEqual(sv.plugins, {})
        self.assertTrue(
            any("rename it to hacker_news.py" in message for message in logs.output)
        )

    def test_load_plugins_warns_with_valid_suggestion_for_hyphenated_invalid_identifier(self):
        """Hyphenated invalid identifiers must get an importable rename suggestion."""
        from sandvoice import SandVoice

        sv = object.__new__(SandVoice)
        sv.config = MagicMock()
        sv.config.plugin_path = "/tmp/plugins"
        sv.plugins = {}

        entries = [self._make_file_entry("123-plugin.py")]
        with patch("sandvoice.os.path.exists", return_value=True), \
             patch("sandvoice.os.scandir", self._make_scandir_mock(entries)), \
             patch("sandvoice.importlib.import_module") as import_module, \
             self.assertLogs("sandvoice", level="WARNING") as logs:
            sv.load_plugins()

        import_module.assert_not_called()
        self.assertEqual(sv.plugins, {})
        self.assertTrue(
            any("rename it to _123_plugin.py" in message for message in logs.output)
        )

    def test_load_plugins_warns_and_skips_non_identifier_filename(self):
        """load_plugins() must skip filenames that are not valid Python identifiers."""
        from sandvoice import SandVoice

        sv = object.__new__(SandVoice)
        sv.config = MagicMock()
        sv.config.plugin_path = "/tmp/plugins"
        sv.plugins = {}

        entries = [self._make_file_entry("123plugin.py")]
        with patch("sandvoice.os.path.exists", return_value=True), \
             patch("sandvoice.os.scandir", self._make_scandir_mock(entries)), \
             patch("sandvoice.importlib.import_module") as import_module, \
             self.assertLogs("sandvoice", level="WARNING") as logs:
            sv.load_plugins()

        import_module.assert_not_called()
        self.assertEqual(sv.plugins, {})
        self.assertTrue(
            any(
                "not a valid Python module identifier" in message and
                "rename it to _123plugin.py" in message
                for message in logs.output
            )
        )

    def test_load_plugins_registers_plugin_process_method(self):
        """load_plugins() must register Plugin().process rather than the instance itself."""
        from sandvoice import SandVoice

        sv = object.__new__(SandVoice)
        sv.config = MagicMock()
        sv.config.plugin_path = "/tmp/plugins"
        sv.plugins = {}

        plugin_instance = MagicMock()
        plugin_instance.process = MagicMock()
        module = MagicMock(spec=["Plugin"])
        module.Plugin = MagicMock(return_value=plugin_instance)

        entries = [self._make_file_entry("weather_plugin.py")]
        with patch("sandvoice.os.path.exists", return_value=True), \
             patch("sandvoice.os.scandir", self._make_scandir_mock(entries)), \
             patch("sandvoice.importlib.import_module", return_value=module):
            sv.load_plugins()

        self.assertIs(sv.plugins["weather_plugin"], plugin_instance.process)
        self.assertIs(sv.plugins["weather-plugin"], plugin_instance.process)

    def test_load_plugins_skips_plugin_without_callable_process_method(self):
        """load_plugins() must skip Plugin classes that do not expose callable process."""
        from sandvoice import SandVoice

        sv = object.__new__(SandVoice)
        sv.config = MagicMock()
        sv.config.plugin_path = "/tmp/plugins"
        sv.plugins = {}

        plugin_instance = MagicMock(spec=[])
        module = MagicMock(spec=["Plugin"])
        module.Plugin = MagicMock(return_value=plugin_instance)

        entries = [self._make_file_entry("weather_plugin.py")]
        with patch("sandvoice.os.path.exists", return_value=True), \
             patch("sandvoice.os.scandir", self._make_scandir_mock(entries)), \
             patch("sandvoice.importlib.import_module", return_value=module), \
             self.assertLogs("sandvoice", level="WARNING") as logs:
            sv.load_plugins()

        self.assertEqual(sv.plugins, {})
        self.assertTrue(
            any("does not expose a callable process function" in message for message in logs.output)
        )

    def test_load_plugins_warns_when_plugin_has_no_supported_entrypoint(self):
        """load_plugins() must warn when a module exposes neither Plugin nor process."""
        from sandvoice import SandVoice

        sv = object.__new__(SandVoice)
        sv.config = MagicMock()
        sv.config.plugin_path = "/tmp/plugins"
        sv.plugins = {}

        module = MagicMock(spec=[])

        entries = [self._make_file_entry("weather_plugin.py")]
        with patch("sandvoice.os.path.exists", return_value=True), \
             patch("sandvoice.os.scandir", self._make_scandir_mock(entries)), \
             patch("sandvoice.importlib.import_module", return_value=module), \
             self.assertLogs("sandvoice", level="WARNING") as logs:
            sv.load_plugins()

        self.assertEqual(sv.plugins, {})
        self.assertTrue(
            any("has no supported entrypoint" in message for message in logs.output)
        )

    def test_load_plugins_warns_and_continues_when_plugin_init_fails(self):
        """load_plugins() must isolate Plugin instantiation failures to that plugin."""
        from sandvoice import SandVoice

        sv = object.__new__(SandVoice)
        sv.config = MagicMock()
        sv.config.plugin_path = "/tmp/plugins"
        sv.plugins = {}

        bad_module = MagicMock(spec=["Plugin"])
        bad_module.Plugin = MagicMock(side_effect=RuntimeError("boom"))
        good_module = MagicMock(spec=["process"])
        good_module.process = MagicMock()

        def import_side_effect(name):
            if name == "plugins.bad_plugin":
                return bad_module
            if name == "plugins.good_plugin":
                return good_module
            raise AssertionError(name)

        entries = [
            self._make_file_entry("bad_plugin.py"),
            self._make_file_entry("good_plugin.py"),
        ]
        with patch("sandvoice.os.path.exists", return_value=True), \
             patch("sandvoice.os.scandir", self._make_scandir_mock(entries)), \
             patch("sandvoice.importlib.import_module", side_effect=import_side_effect), \
             self.assertLogs("sandvoice", level="WARNING") as logs:
            sv.load_plugins()

        self.assertIs(sv.plugins["good_plugin"], good_module.process)
        self.assertIs(sv.plugins["good-plugin"], good_module.process)
        self.assertTrue(
            any("Error initializing plugin bad_plugin" in message and "boom" in message for message in logs.output)
        )

    def test_route_message_normalizes_hyphenated_plugin_name(self):
        """route_message() must normalize hacker-news to the hacker_news plugin key."""
        sv = self._make_stub()
        sv.ai = MagicMock()
        mock_plugin = MagicMock(return_value="plugin output")
        sv.plugins = {"hacker_news": mock_plugin}

        result = sv.route_message("hn", {"route": "hacker-news", "reason": "news"})

        mock_plugin.assert_called_once()
        self.assertEqual(
            mock_plugin.call_args[0][1],
            {"route": "hacker_news", "reason": "news"},
        )
        sv.ai.generate_response.assert_not_called()
        self.assertEqual(result, "plugin output")

    def test_route_message_prefers_canonical_plugin_key_over_hyphen_alias(self):
        """route_message() must dispatch to hacker_news even when hacker-news alias exists."""
        sv = self._make_stub()
        sv.ai = MagicMock()
        canonical_plugin = MagicMock(return_value="canonical")
        alias_plugin = MagicMock(return_value="alias")
        sv.plugins = {
            "hacker_news": canonical_plugin,
            "hacker-news": alias_plugin,
        }

        result = sv.route_message("hn", {"route": "hacker-news", "reason": "news"})

        canonical_plugin.assert_called_once()
        self.assertEqual(
            canonical_plugin.call_args[0][1],
            {"route": "hacker_news", "reason": "news"},
        )
        alias_plugin.assert_not_called()
        sv.ai.generate_response.assert_not_called()
        self.assertEqual(result, "canonical")

    def test_route_message_normalizes_legacy_default_route_name(self):
        """route_message() must normalize default-rote to default-route before dispatch."""
        sv = self._make_stub()
        sv.ai = MagicMock()
        mock_plugin = MagicMock(return_value="plugin output")
        sv.plugins = {"default-route": mock_plugin}

        result = sv.route_message("hello", {"route": "default-rote", "reason": "legacy"})

        mock_plugin.assert_called_once()
        self.assertEqual(
            mock_plugin.call_args[0][1],
            {"route": "default-route", "reason": "legacy"},
        )
        sv.ai.generate_response.assert_not_called()
        self.assertEqual(result, "plugin output")

    def test_scheduler_route_message_normalizes_legacy_default_route_name(self):
        """_scheduler_route_message() must normalize default-rote before plugin dispatch."""
        sv = self._make_stub()
        sv._scheduler_ai = MagicMock()
        sv.ai = MagicMock()
        mock_plugin = MagicMock(return_value="plugin output")
        sv.plugins = {"default-route": mock_plugin}

        result = sv._scheduler_route_message("hello", {"route": "default-rote", "reason": "legacy"})

        mock_plugin.assert_called_once()
        self.assertEqual(
            mock_plugin.call_args[0][1],
            {"route": "default-route", "reason": "legacy"},
        )
        sv._scheduler_ai.generate_response.assert_not_called()
        sv.ai.generate_response.assert_not_called()
        self.assertEqual(result, "plugin output")

    def test_scheduler_route_message_normalizes_hyphenated_plugin_name(self):
        """_scheduler_route_message() must normalize hacker-news to hacker_news."""
        sv = self._make_stub()
        sv._scheduler_ai = MagicMock()
        sv.ai = MagicMock()
        mock_plugin = MagicMock(return_value="plugin output")
        sv.plugins = {"hacker_news": mock_plugin}

        result = sv._scheduler_route_message("hn", {"route": "hacker-news", "reason": "news"})

        mock_plugin.assert_called_once()
        self.assertEqual(
            mock_plugin.call_args[0][1],
            {"route": "hacker_news", "reason": "news"},
        )
        sv._scheduler_ai.generate_response.assert_not_called()
        sv.ai.generate_response.assert_not_called()
        self.assertEqual(result, "plugin output")

    def test_scheduler_route_message_prefers_canonical_plugin_key_over_hyphen_alias(self):
        """_scheduler_route_message() must prefer hacker_news over hacker-news alias."""
        sv = self._make_stub()
        sv._scheduler_ai = MagicMock()
        sv.ai = MagicMock()
        canonical_plugin = MagicMock(return_value="canonical")
        alias_plugin = MagicMock(return_value="alias")
        sv.plugins = {
            "hacker_news": canonical_plugin,
            "hacker-news": alias_plugin,
        }

        result = sv._scheduler_route_message("hn", {"route": "hacker-news", "reason": "news"})

        canonical_plugin.assert_called_once()
        self.assertEqual(
            canonical_plugin.call_args[0][1],
            {"route": "hacker_news", "reason": "news"},
        )
        alias_plugin.assert_not_called()
        sv._scheduler_ai.generate_response.assert_not_called()
        sv.ai.generate_response.assert_not_called()
        self.assertEqual(result, "canonical")

    def test_scheduler_context_route_message_uses_context_ai(self):
        """_SchedulerContext.route_message must route via _route_message_with_ai using
        the context's own AI instance, not the main route_message or directly
        _scheduler_route_message, so each context (scheduler or warmup) uses its own AI."""
        from sandvoice import _SchedulerContext
        sv = self._make_stub()
        context_ai = MagicMock()
        sv._route_message_with_ai = MagicMock(return_value="context routed")
        sv.route_message = MagicMock(return_value="main routed")
        ctx = _SchedulerContext(sv, context_ai)
        result = ctx.route_message("query", {"route": "plugin"})
        sv._route_message_with_ai.assert_called_once_with(context_ai, "query", {"route": "plugin"})
        sv.route_message.assert_not_called()
        self.assertEqual(result, "context routed")


class TestAddTaskPluginNameNormalization(unittest.TestCase):
    """add_task() must strip leading/trailing whitespace from plugin name."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = SchedulerDB(os.path.join(self.tmp, "test.db"))
        self.scheduler = TaskScheduler(
            self.db,
            speak_fn=MagicMock(),
            invoke_plugin_fn=MagicMock(return_value="ok"),
        )

    def tearDown(self):
        self.db.close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_add_task_plugin_name_whitespace_stripped(self):
        """add_task() must normalize plugin name in the persisted task without
        mutating the caller's original dict."""
        payload = {"plugin": "  weather  "}
        task_id = self.scheduler.add_task(
            name="ws-plugin", schedule_type="interval", schedule_value="60",
            action_type="plugin", action_payload=payload,
        )
        # Caller's dict must NOT be mutated
        self.assertEqual(payload["plugin"], "  weather  ")
        # Persisted JSON must have the stripped value
        task = self.db.get_task(task_id)
        self.assertEqual("weather", json.loads(task.action_payload)["plugin"])

    def test_dispatch_plugin_name_stripped_before_invoke(self):
        """_dispatch() must strip plugin_name before calling invoke_plugin_fn."""
        from common.db import SchedulerDB as SDB
        tmp2 = tempfile.mkdtemp()
        try:
            db2 = SDB(os.path.join(tmp2, "t.db"))
            invoke_fn = MagicMock(return_value="ok")
            sched = TaskScheduler(db2, speak_fn=MagicMock(), invoke_plugin_fn=invoke_fn)
            # Manually craft a task with whitespace-padded plugin name in JSON
            task_id = db2.add_task(
                name="pad", schedule_type="interval", schedule_value="60",
                action_type="plugin",
                action_payload={"plugin": "  weather  "},
                next_run=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
            )
            task = db2.get_task(task_id)
            sched._dispatch(task)
            invoke_fn.assert_called_once_with("weather", "", False)
            db2.close()
        finally:
            import shutil
            shutil.rmtree(tmp2, ignore_errors=True)


class TestSyncTasksInputHandling(unittest.TestCase):
    """Input validation and normalization for TaskScheduler.sync_tasks()."""

    def setUp(self):
        self.db = MagicMock()
        self.db.get_all_tasks.return_value = []
        self.scheduler = TaskScheduler(
            db=self.db,
            speak_fn=MagicMock(),
            invoke_plugin_fn=MagicMock(),
        )

    def test_valid_task_is_registered(self):
        self.scheduler.add_task = MagicMock()
        self.scheduler.sync_tasks([{
            "name": "t1",
            "schedule_type": "interval",
            "schedule_value": "60",
            "action_type": "speak",
            "action_payload": {"text": "hello"},
        }])
        self.scheduler.add_task.assert_called_once_with(
            name="t1",
            schedule_type="interval",
            schedule_value="60",
            action_type="speak",
            action_payload={"text": "hello"},
        )

    def test_existing_task_name_is_not_re_registered(self):
        existing = MagicMock()
        existing.name = "existing"
        existing.id = "task-1"
        self.db.get_all_tasks.return_value = [existing]
        self.scheduler.add_task = MagicMock()
        self.scheduler.sync_tasks([{
            "name": "existing",
            "schedule_type": "interval",
            "schedule_value": "60",
            "action_type": "speak",
            "action_payload": {"text": "hi"},
        }])
        self.scheduler.add_task.assert_not_called()
        self.db.delete_task.assert_not_called()

    def test_non_dict_entry_skipped_without_crash(self):
        self.scheduler.add_task = MagicMock()
        self.scheduler.sync_tasks(["not-a-dict", 42, None])
        self.scheduler.add_task.assert_not_called()
        self.db.delete_task.assert_not_called()

    def test_missing_name_is_skipped(self):
        self.scheduler.add_task = MagicMock()
        self.scheduler.sync_tasks([{"schedule_type": "interval", "schedule_value": "60"}])
        self.scheduler.add_task.assert_not_called()

    def test_malformed_task_does_not_crash_scheduler(self):
        self.scheduler.add_task = MagicMock(side_effect=[ValueError("bad config"), None])
        self.scheduler.sync_tasks([
            {"name": "bad", "schedule_type": "interval", "schedule_value": "60",
             "action_type": "speak", "action_payload": {"text": "bad"}},
            {"name": "good", "schedule_type": "interval", "schedule_value": "60",
             "action_type": "speak", "action_payload": {"text": "ok"}},
        ])
        self.assertEqual(self.scheduler.add_task.call_count, 2)

    def test_non_string_name_is_skipped(self):
        self.scheduler.add_task = MagicMock()
        self.scheduler.sync_tasks([{"name": 42, "schedule_type": "interval",
                                    "schedule_value": "60", "action_type": "speak",
                                    "action_payload": {"text": "hi"}}])
        self.scheduler.add_task.assert_not_called()

    def test_null_action_payload_for_speak_is_invalid(self):
        self.scheduler.add_task = MagicMock()
        self.scheduler.sync_tasks([{
            "name": "nullpayload",
            "schedule_type": "interval",
            "schedule_value": "60",
            "action_type": "speak",
            "action_payload": None,
        }])
        self.scheduler.add_task.assert_not_called()

    def test_non_dict_action_payload_for_speak_is_invalid(self):
        self.scheduler.add_task = MagicMock()
        self.scheduler.sync_tasks([{
            "name": "listpayload",
            "schedule_type": "interval",
            "schedule_value": "60",
            "action_type": "speak",
            "action_payload": ["not", "a", "dict"],
        }])
        self.scheduler.add_task.assert_not_called()

    def test_name_whitespace_stripped_before_registration(self):
        self.scheduler.add_task = MagicMock()
        self.scheduler.sync_tasks([{
            "name": "  my-task  ",
            "schedule_type": "interval",
            "schedule_value": "60",
            "action_type": "speak",
            "action_payload": {"text": "hi"},
        }])
        self.scheduler.add_task.assert_called_once()
        self.assertEqual(self.scheduler.add_task.call_args.kwargs["name"], "my-task")


class TestResolveTz(unittest.TestCase):
    """Tests for TaskScheduler._resolve_tz() warning paths."""

    def test_none_tz_returns_none_silently(self):
        self.assertIsNone(TaskScheduler._resolve_tz(None))

    def test_empty_tz_returns_none_silently(self):
        self.assertIsNone(TaskScheduler._resolve_tz(""))

    def test_invalid_tz_returns_none_and_warns(self):
        with self.assertLogs("common.scheduler", level="WARNING") as cm:
            result = TaskScheduler._resolve_tz("Not/AValid_Timezone")
        self.assertIsNone(result)
        self.assertTrue(any("could not be resolved" in line for line in cm.output))

    def test_valid_tz_returns_zoneinfo(self):
        from zoneinfo import ZoneInfo
        result = TaskScheduler._resolve_tz("America/Toronto")
        self.assertIsInstance(result, ZoneInfo)


class TestWarmupCache(unittest.TestCase):
    """Tests for SandVoice._warmup_cache()."""

    def _make_stub(self, cache_auto_refresh=None, cache_enabled=True, scheduler=None,
                   warmup_timeout=0, warmup_retries=1, warmup_retry_delay=0.0):
        from sandvoice import SandVoice
        sv = object.__new__(SandVoice)
        sv.config = MagicMock()
        sv.config.cache_enabled = cache_enabled
        sv.config.cache_auto_refresh = cache_auto_refresh or []
        sv.config.cache_warmup_timeout_s = warmup_timeout
        sv.config.cache_warmup_retries = warmup_retries
        sv.config.cache_warmup_retry_delay_s = warmup_retry_delay
        sv.cache = MagicMock() if cache_enabled else None
        sv.scheduler = scheduler
        sv.plugins = {}
        sv._ai_audio_lock = threading.Lock()
        sv._scheduler_ai = None
        sv._scheduler_audio = None
        sv._warmup_threads = []
        sv._warmup_timeout = warmup_timeout
        sv._warmup_plugin_names = []
        return sv

    def test_no_entries_returns_immediately(self):
        sv = self._make_stub(cache_auto_refresh=[])
        # Should complete without error or thread launch
        sv._warmup_cache()

    def test_cache_disabled_skips_warmup(self):
        sv = self._make_stub(
            cache_auto_refresh=[{"plugin": "news", "interval_s": 7200, "ttl_s": 7200, "max_stale_s": 10800, "query": "news"}],
            cache_enabled=False,
        )
        sv._warmup_cache()  # must not raise

    def test_unknown_plugin_skipped(self):
        sv = self._make_stub(cache_auto_refresh=[
            {"plugin": "nonexistent", "interval_s": 3600, "ttl_s": 3600, "max_stale_s": 5400, "query": "nonexistent"},
        ])
        sv._warmup_cache()  # must not raise; plugin not in sv.plugins

    def test_plugin_without_cache_key_skipped(self):
        """Plugin missing _cache_key() must be skipped — no warmup thread launched."""
        from sandvoice import SandVoice
        sv = self._make_stub()
        # Add a plugin that exists but has no _cache_key
        sv.plugins["echo"] = MagicMock()
        sv.config.cache_auto_refresh = [
            {"plugin": "echo", "interval_s": 3600, "ttl_s": 3600, "max_stale_s": 5400, "query": "echo"},
        ]
        with patch("sandvoice._derive_cache_key", return_value=None):
            sv._warmup_cache()
        sv.plugins["echo"].assert_not_called()

    def test_warmup_thread_launched_for_valid_entry(self):
        """A valid entry with a known plugin and _cache_key must launch a warmup thread."""
        import sys
        sv = self._make_stub()
        plugin_fn = MagicMock(return_value=None)
        sv.plugins["news"] = plugin_fn

        launched = []

        def fake_thread(target, name, daemon):
            launched.append(name)
            return MagicMock()

        sv.config.cache_auto_refresh = [
            {"plugin": "news", "interval_s": 7200, "ttl_s": 7200, "max_stale_s": 10800, "query": "news"},
        ]
        with patch("sandvoice._derive_cache_key", return_value="news:https://rss.example.com"), \
             patch("sandvoice.threading.Thread", side_effect=fake_thread):
            sv._warmup_cache()

        self.assertEqual(len(launched), 1)
        self.assertIn("cache-warmup-news-0", launched)

    def test_thread_names_unique_for_same_plugin(self):
        """Multiple entries for the same plugin must get unique thread names."""
        sv = self._make_stub()
        sv.plugins["news"] = MagicMock(return_value=None)
        sv.config.cache_auto_refresh = [
            {"plugin": "news", "interval_s": 7200, "ttl_s": 7200, "max_stale_s": 10800, "query": "news 1"},
            {"plugin": "news", "interval_s": 3600, "ttl_s": 3600, "max_stale_s": 5400, "query": "news 2"},
        ]

        launched = []

        def fake_thread(target, name, daemon):
            launched.append(name)
            return MagicMock()

        with patch("sandvoice._derive_cache_key", return_value="news:key"), \
             patch("sandvoice.threading.Thread", side_effect=fake_thread):
            sv._warmup_cache()

        self.assertEqual(launched, ["cache-warmup-news-0", "cache-warmup-news-1"])

    def test_override_entry_skips_scheduler_task(self):
        """Entries with rss_url/location/unit overrides must skip periodic task registration."""
        sv = self._make_stub()
        sv.plugins["news"] = MagicMock(return_value=None)
        mock_scheduler = MagicMock()
        sv.scheduler = mock_scheduler
        sv.config.cache_auto_refresh = [
            {"plugin": "news", "interval_s": 7200, "ttl_s": 7200, "max_stale_s": 10800,
             "query": "news", "rss_url": "https://custom.feed/rss.xml"},
        ]

        with patch("sandvoice._derive_cache_key", return_value="news:https://custom.feed/rss.xml"), \
             patch("sandvoice.threading.Thread", return_value=MagicMock()):
            sv._warmup_cache()

        mock_scheduler.add_task.assert_not_called()

    def test_warmup_blocks_until_threads_finish(self):
        """When timeout > 0, _join_warmup_threads() must join all warmup threads."""
        sv = self._make_stub(warmup_timeout=5)
        sv.plugins["news"] = MagicMock(return_value=None)
        sv.config.cache_auto_refresh = [
            {"plugin": "news", "interval_s": 7200, "ttl_s": 7200, "max_stale_s": 10800, "query": "news"},
        ]

        join_called = []
        mock_thread = MagicMock()
        mock_thread.join.side_effect = lambda timeout: join_called.append(timeout)
        mock_thread.is_alive.return_value = False  # thread finished cleanly → "done" log path

        with patch("sandvoice._derive_cache_key", return_value="news:key"), \
             patch("sandvoice.threading.Thread", return_value=mock_thread):
            sv._warmup_cache()
        sv._join_warmup_threads()

        self.assertTrue(len(join_called) == 1)
        self.assertGreater(join_called[0], 0)

    def test_warmup_continues_after_timeout(self):
        """When the timeout budget is exhausted, remaining threads are not joined."""
        sv = self._make_stub(warmup_timeout=0.001)  # 1ms — will expire almost immediately
        sv.plugins["news"] = MagicMock(return_value=None)
        sv.config.cache_auto_refresh = [
            {"plugin": "news", "interval_s": 7200, "ttl_s": 7200, "max_stale_s": 10800, "query": "news 1"},
            {"plugin": "news", "interval_s": 3600, "ttl_s": 3600, "max_stale_s": 5400, "query": "news 2"},
        ]

        join_calls = []

        def slow_join(timeout):
            import time as _time
            _time.sleep(0.01)  # longer than the timeout budget
            join_calls.append(timeout)

        created_threads = []

        def make_mock_thread(*args, **kwargs):
            t = MagicMock()
            t.join.side_effect = slow_join
            t.is_alive.return_value = True  # timeout exhausted → threads still running
            created_threads.append(t)
            return t

        with patch("sandvoice._derive_cache_key", return_value="news:key"), \
             patch("sandvoice.threading.Thread", side_effect=make_mock_thread):
            sv._warmup_cache()
        sv._join_warmup_threads()

        # At least one join was attempted before the timeout budget was exhausted.
        self.assertGreaterEqual(len(join_calls), 1)
        # Two distinct thread objects were created and each started once.
        self.assertEqual(len(created_threads), 2)
        self.assertTrue(all(t.start.call_count == 1 for t in created_threads))

    def test_warmup_timeout_zero_fires_and_forgets(self):
        """When cache_warmup_timeout_s is 0, threads are started but never joined."""
        sv = self._make_stub(warmup_timeout=0)
        sv.plugins["news"] = MagicMock(return_value=None)
        sv.config.cache_auto_refresh = [
            {"plugin": "news", "interval_s": 7200, "ttl_s": 7200, "max_stale_s": 10800, "query": "news"},
        ]

        mock_thread = MagicMock()

        with patch("sandvoice._derive_cache_key", return_value="news:key"), \
             patch("sandvoice.threading.Thread", return_value=mock_thread):
            sv._warmup_cache()
        sv._join_warmup_threads()  # timeout=0, so must not join

        mock_thread.start.assert_called_once()
        mock_thread.join.assert_not_called()

    def test_warmup_retries_on_failure(self):
        """Plugin raises on first call, succeeds on second; must be called twice."""
        import threading as _threading
        _RealThread = _threading.Thread

        call_count = []

        def flaky_plugin(query, route, ctx):
            call_count.append(1)
            if len(call_count) == 1:
                raise RuntimeError("transient failure")

        sv = self._make_stub(warmup_timeout=0, warmup_retries=3, warmup_retry_delay=0.0)
        sv.plugins["news"] = flaky_plugin
        sv.config.cache_auto_refresh = [
            {"plugin": "news", "interval_s": 7200, "ttl_s": 7200, "max_stale_s": 10800, "query": "news"},
        ]

        threads = []

        def real_thread(target, name, daemon):
            t = _RealThread(target=target, name=name, daemon=daemon)
            threads.append(t)
            return t

        with patch("sandvoice._derive_cache_key", return_value="news:key"), \
             patch("sandvoice.AI"), \
             patch("sandvoice.resolve_plugin_route_name", return_value="news"), \
             patch("sandvoice._SchedulerContext"), \
             patch("sandvoice.threading.Thread", side_effect=real_thread):
            sv._warmup_cache()
            for t in threads:
                t.join(timeout=5)

        self.assertEqual(len(call_count), 2)

    def test_warmup_gives_up_after_max_retries(self):
        """Plugin always raises; must be called cache_warmup_retries times, then WARNING logged."""
        import threading as _threading
        _RealThread = _threading.Thread

        call_count = []

        def always_failing_plugin(query, route, ctx):
            call_count.append(1)
            raise RuntimeError("always fails")

        # Use a positive timeout so _warmup_cache() joins the thread before
        # returning, guaranteeing the WARNING is captured inside assertLogs.
        sv = self._make_stub(warmup_timeout=5, warmup_retries=3, warmup_retry_delay=0.0)
        sv.plugins["news"] = always_failing_plugin
        sv.config.cache_auto_refresh = [
            {"plugin": "news", "interval_s": 7200, "ttl_s": 7200, "max_stale_s": 10800, "query": "news"},
        ]

        def real_thread(target, name, daemon):
            t = _RealThread(target=target, name=name, daemon=daemon)
            return t

        with patch("sandvoice._derive_cache_key", return_value="news:key"), \
             patch("sandvoice.AI"), \
             patch("sandvoice.resolve_plugin_route_name", return_value="news"), \
             patch("sandvoice._SchedulerContext"), \
             patch("sandvoice.threading.Thread", side_effect=real_thread), \
             self.assertLogs("sandvoice", level="WARNING") as cm:
            sv._warmup_cache()
            sv._join_warmup_threads()

        self.assertEqual(len(call_count), 3)
        self.assertTrue(any("failed after" in line for line in cm.output))


if __name__ == "__main__":
    unittest.main()
