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
        result = calc_next_run("cron", "* * * * *")
        parsed = datetime.fromisoformat(result)
        self.assertGreater(parsed, datetime.now(timezone.utc))

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

    def test_scheduler_context_route_message_uses_scheduler_route(self):
        """_SchedulerContext.route_message must delegate to _scheduler_route_message,
        not SandVoice.route_message, so plugins calling ctx.route_message() still
        use the scheduler AI."""
        from sandvoice import _SchedulerContext
        sv = self._make_stub()
        sv._scheduler_ai = MagicMock()
        sv.ai = MagicMock()
        sv._scheduler_route_message = MagicMock(return_value="scheduler routed")
        sv.route_message = MagicMock(return_value="main routed")
        ctx = _SchedulerContext(sv, sv._scheduler_ai)
        result = ctx.route_message("query", {"route": "plugin"})
        sv._scheduler_route_message.assert_called_once_with("query", {"route": "plugin"})
        sv.route_message.assert_not_called()
        self.assertEqual(result, "scheduler routed")


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


if __name__ == "__main__":
    unittest.main()
