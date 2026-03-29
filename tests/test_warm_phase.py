import logging
import unittest
from unittest.mock import Mock

from common.warm_phase import WarmPhase, WarmTask


class TestWarmTask(unittest.TestCase):
    def test_defaults(self):
        fn = Mock()
        task = WarmTask("my-task", fn)
        self.assertEqual(task.name, "my-task")
        self.assertIs(task.fn, fn)
        self.assertTrue(task.required)

    def test_optional(self):
        task = WarmTask("optional", Mock(), required=False)
        self.assertFalse(task.required)


class TestWarmPhaseRun(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def test_empty_tasks_does_not_raise(self):
        WarmPhase([]).run()

    def test_all_succeed(self):
        a = Mock()
        b = Mock()
        WarmPhase([WarmTask("a", a), WarmTask("b", b)]).run()
        a.assert_called_once()
        b.assert_called_once()

    def test_required_failure_raises(self):
        def fail():
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError) as ctx:
            WarmPhase([WarmTask("bad", fail, required=True)]).run()
        self.assertIn("boot failed", str(ctx.exception).lower())
        self.assertIn("bad", str(ctx.exception))
        self.assertIn("boom", str(ctx.exception))

    def test_optional_failure_does_not_raise(self):
        def fail():
            raise RuntimeError("optional fail")

        good = Mock()
        # Should not raise
        WarmPhase([
            WarmTask("good", good, required=True),
            WarmTask("optional", fail, required=False),
        ]).run()
        good.assert_called_once()

    def test_multiple_required_failures_all_reported(self):
        def fail_a():
            raise RuntimeError("err-a")

        def fail_b():
            raise RuntimeError("err-b")

        with self.assertRaises(RuntimeError) as ctx:
            WarmPhase([
                WarmTask("task-a", fail_a),
                WarmTask("task-b", fail_b),
            ]).run()
        msg = str(ctx.exception)
        self.assertIn("task-a", msg)
        self.assertIn("task-b", msg)

    def test_success_and_required_failure(self):
        good = Mock()

        def fail():
            raise ValueError("bad value")

        with self.assertRaises(RuntimeError):
            WarmPhase([
                WarmTask("good", good),
                WarmTask("bad", fail),
            ]).run()
        good.assert_called_once()


if __name__ == "__main__":
    unittest.main()
