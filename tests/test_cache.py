import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from common.cache import CacheEntry, VoiceCache


class TestVoiceCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test_cache.db")
        self.cache = VoiceCache(self.db_path)

    def tearDown(self):
        self.cache.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── schema / init ────────────────────────────────────────────────────────

    def test_db_file_created(self):
        self.assertTrue(os.path.exists(self.db_path))

    def test_creates_parent_dirs(self):
        nested = os.path.join(self.tmp, "a", "b", "cache.db")
        c = VoiceCache(nested)
        self.assertTrue(os.path.exists(nested))
        c.close()

    # ── get / set ────────────────────────────────────────────────────────────

    def test_get_missing_key_returns_none(self):
        self.assertIsNone(self.cache.get("no-such-key"))

    def test_set_and_get(self):
        self.cache.set("k1", '{"temp": 20}', ttl_s=3600, max_stale_s=7200)
        entry = self.cache.get("k1")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.key, "k1")
        self.assertEqual(entry.value, '{"temp": 20}')
        self.assertEqual(entry.ttl_s, 3600)
        self.assertEqual(entry.max_stale_s, 7200)

    def test_set_updates_existing_entry(self):
        self.cache.set("k1", "old", ttl_s=100, max_stale_s=200)
        self.cache.set("k1", "new", ttl_s=999, max_stale_s=1998)
        entry = self.cache.get("k1")
        self.assertEqual(entry.value, "new")
        self.assertEqual(entry.ttl_s, 999)

    def test_set_with_timestamp_stores_explicit_time(self):
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        self.cache.set_with_timestamp("k1", "v", ttl_s=3600, max_stale_s=7200, updated_at=old_ts)
        entry = self.cache.get("k1")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.updated_at, old_ts)
        self.assertGreater(self.cache.age_s(entry), 4 * 3600)

    def test_updated_at_is_iso8601_utc(self):
        self.cache.set("k1", "v", ttl_s=60, max_stale_s=120)
        entry = self.cache.get("k1")
        parsed = datetime.fromisoformat(entry.updated_at)
        # Should parse without error and be close to now
        now = datetime.now(timezone.utc)
        self.assertLessEqual(abs((now - parsed).total_seconds()), 5)

    # ── age_s ────────────────────────────────────────────────────────────────

    def test_age_s_fresh_entry_is_small(self):
        self.cache.set("k1", "v", ttl_s=3600, max_stale_s=7200)
        entry = self.cache.get("k1")
        self.assertLess(self.cache.age_s(entry), 2)

    def test_age_s_old_entry(self):
        old_time = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
        entry = CacheEntry(
            key="k", value="v", updated_at=old_time, ttl_s=3600, max_stale_s=21600
        )
        self.assertGreater(self.cache.age_s(entry), 3 * 3600)

    # ── is_fresh ─────────────────────────────────────────────────────────────

    def test_is_fresh_new_entry(self):
        self.cache.set("k1", "v", ttl_s=3600, max_stale_s=7200)
        entry = self.cache.get("k1")
        self.assertTrue(self.cache.is_fresh(entry))

    def test_is_fresh_expired_entry(self):
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=7200)).isoformat()
        entry = CacheEntry(key="k", value="v", updated_at=old_time, ttl_s=3600, max_stale_s=21600)
        self.assertFalse(self.cache.is_fresh(entry))

    # ── can_serve ────────────────────────────────────────────────────────────

    def test_can_serve_fresh_entry(self):
        self.cache.set("k1", "v", ttl_s=3600, max_stale_s=21600)
        entry = self.cache.get("k1")
        self.assertTrue(self.cache.can_serve(entry))

    def test_can_serve_stale_within_max_stale(self):
        # 5 hours old, ttl=3h, max_stale=6h → stale but still serveable
        old_time = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        entry = CacheEntry(key="k", value="v", updated_at=old_time, ttl_s=10800, max_stale_s=21600)
        self.assertFalse(self.cache.is_fresh(entry))
        self.assertTrue(self.cache.can_serve(entry))

    def test_cannot_serve_beyond_max_stale(self):
        # 7 hours old, max_stale=6h
        old_time = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
        entry = CacheEntry(key="k", value="v", updated_at=old_time, ttl_s=10800, max_stale_s=21600)
        self.assertFalse(self.cache.can_serve(entry))

    # ── close ────────────────────────────────────────────────────────────────

    def test_close_is_idempotent(self):
        # Should not raise even if called twice; _conn must be None after first close
        self.cache.close()
        self.assertIsNone(self.cache._conn)
        self.cache.close()  # second call must also be safe

    # ── shared DB with SchedulerDB ────────────────────────────────────────────

    def test_cache_coexists_with_scheduler_db(self):
        from common.db import SchedulerDB
        db = SchedulerDB(self.db_path)
        task_id = db.add_task(
            name="t1", schedule_type="interval", schedule_value="60",
            action_type="speak", action_payload={"text": "hi"},
            next_run=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        )
        self.cache.set("weather:London:metric", '{"temp": 15}', ttl_s=3600, max_stale_s=7200)
        # Both reads should work without conflict
        task = db.get_task(task_id)
        entry = self.cache.get("weather:London:metric")
        self.assertEqual(task.name, "t1")
        self.assertIsNotNone(entry)
        db.close()

    # ── age_s robustness ─────────────────────────────────────────────────────

    def test_age_s_handles_z_suffix(self):
        """age_s must parse 'Z'-suffixed timestamps without raising."""
        entry = CacheEntry(
            key="k", value="v",
            updated_at=(datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            ttl_s=3600, max_stale_s=7200,
        )
        age = self.cache.age_s(entry)
        self.assertGreater(age, 0)
        self.assertLess(age, 7200)

    def test_age_s_treats_invalid_timestamp_as_inf(self):
        """age_s must return float('inf') for unparseable updated_at."""
        entry = CacheEntry(key="k", value="v", updated_at="not-a-date", ttl_s=3600, max_stale_s=7200)
        self.assertEqual(self.cache.age_s(entry), float("inf"))

    def test_age_s_treats_naive_datetime_as_utc(self):
        """age_s must treat naive timestamps as UTC, not raise."""
        naive_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
        entry = CacheEntry(key="k", value="v", updated_at=naive_ts, ttl_s=3600, max_stale_s=7200)
        age = self.cache.age_s(entry)
        self.assertGreater(age, 0)
        self.assertLess(age, 10800)

    # ── closed-cache guards ───────────────────────────────────────────────────

    def test_get_after_close_returns_none(self):
        self.cache.set("k", "v", ttl_s=60, max_stale_s=120)
        self.cache.close()
        self.assertIsNone(self.cache.get("k"))

    def test_set_after_close_does_not_raise(self):
        self.cache.close()
        # Should log a warning and return without crashing
        self.cache.set("k", "v", ttl_s=60, max_stale_s=120)
