import concurrent.futures
import logging

logger = logging.getLogger(__name__)


class WarmTask:
    """A single task in the boot warm phase.

    Args:
        name:     Human-readable name used in log messages and error reports.
        fn:       Zero-argument callable to execute.
        required: When True a failure raises RuntimeError and aborts boot.
                  When False a failure logs a warning and boot continues.
    """

    __slots__ = ("name", "fn", "required")

    def __init__(self, name, fn, required=True):
        self.name = name
        self.fn = fn
        self.required = required


class WarmPhase:
    """Parallel boot sequence that blocks until all tasks finish.

    Required tasks cause a ``RuntimeError`` on failure, aborting startup.
    Optional tasks log a warning and allow startup to continue.

    Designed for extensibility: future tasks (cache prefill, connectivity
    checks, ML model loading) slot in alongside existing ones without any
    changes to the boot call site.

    Usage::

        warm = WarmPhase([
            WarmTask("voice-filler", filler_cache.warm, required=True),
        ])
        warm.run()   # blocks; raises RuntimeError on required failure
    """

    def __init__(self, tasks):
        self.tasks = list(tasks)

    def run(self):
        """Run all tasks in parallel.  Raises RuntimeError if any required task fails."""
        if not self.tasks:
            return

        failures = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self.tasks)) as executor:
            future_to_task = {executor.submit(task.fn): task for task in self.tasks}
            for future in concurrent.futures.as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    future.result()
                    logger.debug("Warm task '%s' completed", task.name)
                except Exception as e:
                    if task.required:
                        failures[task.name] = e
                    else:
                        logger.warning("Optional warm task '%s' failed: %s", task.name, e)

        if failures:
            msg = "; ".join(f"{name}: {e}" for name, e in failures.items())
            raise RuntimeError(f"Boot failed during warm phase: {msg}")
