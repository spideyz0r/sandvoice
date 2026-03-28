#!/usr/bin/env python3
import warnings
# Suppress pygame's pkg_resources deprecation warning (pygame issue, not ours)
warnings.filterwarnings("ignore", message="pkg_resources is deprecated")

from common.configuration import Config
from common.audio import Audio
from common.ai import AI, normalize_route_name, pop_streaming_chunk
from common.error_handling import handle_api_error
from common.cache import VoiceCache
from common.db import SchedulerDB
from common.scheduler import TaskScheduler
from common.plugin_loader import load_manifest, check_env_vars, build_extra_routes_text

import argparse, atexit, importlib, importlib.util, logging, os, signal, sys
import queue, threading, time
import re

logger = logging.getLogger(__name__)


def normalize_plugin_name(name):
    """Convert route/plugin names to the canonical Python module key."""
    if not isinstance(name, str):
        return name
    return name.strip().replace("-", "_")


def is_valid_plugin_module_name(name):
    """Return True when a plugin filename maps to a valid Python module identifier."""
    return isinstance(name, str) and bool(name) and name.isidentifier()


def suggested_plugin_module_name(name):
    """Return a valid Python module name suggestion for an invalid plugin filename."""
    if not isinstance(name, str):
        return "plugin_module"
    candidate = normalize_plugin_name(name)
    candidate = re.sub(r"[^A-Za-z0-9_]", "_", candidate)
    if not candidate:
        return "plugin_module"
    if candidate[0].isdigit():
        candidate = "_" + candidate
    return candidate


def plugin_route_alias(name):
    """Return the voice-friendly hyphenated alias for a plugin module key."""
    if not isinstance(name, str):
        return name
    return name.replace("_", "-")


def resolve_plugin_route_name(route_name, plugins):
    """Resolve a route name to the best matching plugin key."""
    normalized_route = normalize_route_name(route_name)
    plugin_name = normalize_plugin_name(normalized_route)
    if plugin_name in plugins:
        return plugin_name

    return normalized_route

class _SchedulerContext:
    """Proxy passed to plugins when invoked from the scheduler.

    Exposes the scheduler-dedicated AI instance as `.ai` so plugins don't
    accidentally mutate the interactive conversation history.
    All other attributes delegate to the underlying SandVoice instance.
    """

    def __init__(self, base, scheduler_ai):
        self._base = base
        self.ai = scheduler_ai

    def route_message(self, *args, **kwargs):
        """Route messages via the scheduler AI to avoid polluting interactive history."""
        return self._base._scheduler_route_message(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._base, name)


class SandVoice:
    def __init__(self):
        self.parse_args()
        self.config = Config()
        self.ai = AI(self.config)
        if not os.path.exists(self.config.tmp_files_path):
            os.makedirs(self.config.tmp_files_path)
        self.plugins = {}
        self._plugin_manifests = []
        self.load_plugins()
        self._ai_audio_lock = threading.Lock()
        self._scheduler_audio = None  # lazily created on first scheduler voice task
        self._scheduler_ai = None  # set by _init_scheduler() on success; None when disabled
        self.cache = self._init_cache()
        self.scheduler = self._init_scheduler()
        if self.args.cli:
            self.config.cli_input = True

    def parse_args(self):
        self.parser = argparse.ArgumentParser(
            description='SandVoice - Voice assistant with multiple modes'
        )

        mode_group = self.parser.add_mutually_exclusive_group()
        mode_group.add_argument(
            '--cli',
            action='store_true',
            help='enter cli mode (text input only, no microphone recording; audio output such as TTS may still be used)'
        )
        mode_group.add_argument(
            '--wake-word',
            action='store_true',
            help='enter wake word mode (hands-free voice activation with "hey sandvoice")'
        )
        self.args = self.parser.parse_args()

    def load_plugins(self):
        if not os.path.exists(self.config.plugin_path):
            print(f"Plugin path {self.config.plugin_path} does not exist")
            exit(1)
        logger.debug("Loading plugins from %s", self.config.plugin_path)
        self._plugin_manifests = []
        with os.scandir(self.config.plugin_path) as it:
            entries = sorted(it, key=lambda e: e.name)
        folder_manifest_stems = {
            e.name for e in entries
            if e.is_dir() and os.path.isfile(os.path.join(e.path, "plugin.yaml"))
        }
        for entry in entries:
            if entry.is_dir():
                self._load_plugin_folder(entry)
            elif entry.name.endswith(".py"):
                stem = os.path.splitext(entry.name)[0]
                if normalize_plugin_name(stem) in {normalize_plugin_name(s) for s in folder_manifest_stems}:
                    logger.debug(
                        "Skipping legacy single-file plugin %s: folder plugin with manifest exists",
                        entry.name,
                    )
                    continue
                self._load_plugin_file(entry)
        self.config.merge_plugin_defaults(self._plugin_manifests)

    def _load_plugin_file(self, entry):
        """Load a single-file .py plugin (backward-compatible path)."""
        filename = entry.name
        try:
            raw_module_name = os.path.splitext(filename)[0]
            module_name = normalize_plugin_name(raw_module_name)
            if raw_module_name != module_name:
                suggested_name = (
                    module_name
                    if is_valid_plugin_module_name(module_name)
                    else suggested_plugin_module_name(raw_module_name)
                )
                logger.warning(
                    "Plugin filename %s is not underscore-safe; rename it to %s.py",
                    filename,
                    suggested_name,
                )
                return
            if not is_valid_plugin_module_name(module_name):
                suggested_name = suggested_plugin_module_name(raw_module_name)
                logger.warning(
                    "Plugin filename %s is not a valid Python module identifier; rename it to %s.py",
                    filename,
                    suggested_name,
                )
                return
            module = importlib.import_module(f"plugins.{module_name}")
        except Exception as e:
            logger.warning("Error loading plugin %s: %s", filename, e)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Plugin load traceback for %s", filename, exc_info=True)
            return
        self._register_plugin_module(module, module_name, source_label=filename)

    def _load_plugin_folder(self, entry):
        """Load a folder-based plugin driven by a plugin.yaml manifest."""
        folder_path = entry.path
        folder_name = entry.name
        if folder_name.startswith("_"):
            return

        manifest = load_manifest(folder_path)
        if manifest is None:
            logger.debug("No valid plugin.yaml in %s; skipping folder", folder_path)
            return

        module_name = normalize_plugin_name(manifest.name)
        if module_name != normalize_plugin_name(folder_name):
            logger.warning(
                "Plugin folder '%s' manifest name '%s' does not match folder name; skipping",
                folder_name,
                manifest.name,
            )
            return

        missing = check_env_vars(manifest)
        if missing:
            noun = "vars" if len(missing) > 1 else "var"
            print(
                f"[sandvoice] {manifest.name} plugin disabled: "
                f"missing env {noun} {', '.join(missing)}"
            )
            logger.warning(
                "Plugin '%s' disabled: missing env vars: %s",
                manifest.name,
                ", ".join(missing),
            )
            return

        plugin_py = os.path.join(folder_path, "plugin.py")
        if not os.path.isfile(plugin_py):
            logger.warning(
                "Plugin folder %s has plugin.yaml but no plugin.py; skipping", folder_path
            )
            return
        full_module_name = f"plugins.{module_name}.plugin"
        try:
            module = importlib.import_module(full_module_name)
        except ModuleNotFoundError as e:
            missing = getattr(e, "name", None) or ""
            if not full_module_name.startswith(missing):
                # ImportError from inside the plugin, not a missing package — do not retry
                logger.warning("Error loading plugin folder %s: %s", folder_name, e)
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("Plugin load traceback for %s", folder_name, exc_info=True)
                return
            spec = importlib.util.spec_from_file_location(full_module_name, plugin_py)
            if spec is None or spec.loader is None:
                logger.warning("Error loading plugin folder %s: could not create module spec", folder_name)
                return
            try:
                module = importlib.util.module_from_spec(spec)
                sys.modules[full_module_name] = module
                spec.loader.exec_module(module)
            except Exception as e:
                sys.modules.pop(full_module_name, None)
                logger.warning("Error loading plugin folder %s: %s", folder_name, e)
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug("Plugin load traceback for %s", folder_name, exc_info=True)
                return
        except Exception as e:
            logger.warning("Error loading plugin folder %s: %s", folder_name, e)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Plugin load traceback for %s", folder_name, exc_info=True)
            return

        if self._register_plugin_module(module, module_name, folder_name):
            self._plugin_manifests.append(manifest)

    def _register_plugin_module(self, module, module_name, source_label=None):
        """Register a loaded module's callable. Returns True on success.

        Args:
            module:       Loaded module object.
            module_name:  Pre-normalised module name used as the plugin dict key.
            source_label: Human-readable name for log messages (defaults to module_name).
        """
        label = source_label or module_name
        try:
            if hasattr(module, "Plugin"):
                plugin_instance = module.Plugin()
                plugin = getattr(plugin_instance, "process", None)
            elif hasattr(module, "process"):
                plugin = module.process
            else:
                logger.warning(
                    "Plugin %s has no supported entrypoint; expected Plugin or process",
                    label,
                )
                return False
        except Exception as e:
            logger.warning("Error initializing plugin %s: %s", label, e)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Plugin init traceback for %s", label, exc_info=True)
            return False

        if not callable(plugin):
            logger.warning(
                "Plugin %s does not expose a callable process function; skipping",
                label,
            )
            return False

        self.plugins[module_name] = plugin
        alias = plugin_route_alias(module_name)
        if alias != module_name:
            self.plugins[alias] = plugin
        return True

    def _init_cache(self):
        """Initialise VoiceCache if cache_enabled, using the same DB file as the scheduler."""
        if not self.config.cache_enabled:
            return None
        try:
            cache = VoiceCache(self.config.scheduler_db_path)
            logger.info("Voice cache enabled (db=%s)", self.config.scheduler_db_path)
            return cache
        except Exception as e:
            logger.warning("Voice cache disabled — failed to initialise: %s", e)
            return None

    def _init_scheduler(self):
        if not self.config.scheduler_enabled:
            return None
        ai = None
        db = None
        try:
            ai = AI(self.config)
            db = SchedulerDB(self.config.scheduler_db_path)
            scheduler = TaskScheduler(
                db=db,
                speak_fn=self._scheduler_speak,
                invoke_plugin_fn=self._scheduler_invoke_plugin,
                poll_interval_s=self.config.scheduler_poll_interval,
                tz=self.config.timezone,
            )
            self._scheduler_ai = ai
            if self.config.tasks_file_exists:
                scheduler.sync_tasks(self.config.tasks)
            else:
                logger.info(
                    "Tasks file not found at %s; skipping scheduler DB sync",
                    self.config.tasks_file_path,
                )
            return scheduler
        except Exception as e:
            logger.warning("Scheduler disabled — failed to initialize: %s", e)
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass
            self._scheduler_ai = None
            return None

    def _scheduler_speak(self, text):
        if not text or not self.config.bot_voice:
            return
        tts_files = self._scheduler_ai.text_to_speech(text)
        if not tts_files:
            return
        with self._ai_audio_lock:
            if self._scheduler_audio is None:
                self._scheduler_audio = Audio(self.config)
            success, failed_file, error = self._scheduler_audio.play_audio_files(tts_files)
            if not success:
                logger.warning("Scheduler speak: audio playback failed for '%s': %s", failed_file, error)

    def _scheduler_invoke_plugin(self, plugin_name, query, refresh_only):
        route = {"route": plugin_name, "refresh_only": refresh_only}
        result = self._scheduler_route_message(query or plugin_name, route)
        if not refresh_only and self.config.bot_voice and result:
            tts_files = self._scheduler_ai.text_to_speech(result)
            if tts_files:
                with self._ai_audio_lock:
                    if self._scheduler_audio is None:
                        self._scheduler_audio = Audio(self.config)
                    success, failed_file, error = self._scheduler_audio.play_audio_files(tts_files)
                    if not success:
                        logger.warning("Scheduler plugin: audio playback failed for '%s': %s", failed_file, error)
        return result

    def _scheduler_route_message(self, user_input, route):
        """Route a scheduler-triggered message using a dedicated AI instance to avoid
        polluting the interactive conversation history."""
        normalized_route = dict(route)
        normalized_route["route"] = resolve_plugin_route_name(route.get("route"), self.plugins)
        logger.debug("Route: %s -> %s", route, normalized_route)
        logger.debug("Plugins: %s", self.plugins.keys())
        if normalized_route["route"] in self.plugins:
            ctx = _SchedulerContext(self, self._scheduler_ai)
            return self.plugins[normalized_route["route"]](user_input, normalized_route, ctx)
        else:
            return self._scheduler_ai.generate_response(user_input).content

    def route_message(self, user_input, route):
        normalized_route = dict(route)
        normalized_route["route"] = resolve_plugin_route_name(route.get("route"), self.plugins)
        logger.debug("Route: %s -> %s", route, normalized_route)
        logger.debug("Plugins: %s", self.plugins.keys())
        if normalized_route["route"] in self.plugins:
            return self.plugins[normalized_route["route"]](user_input, normalized_route, self)
        else:
            return self.ai.generate_response(user_input).content

    def runIt(self):
        if self.config.cli_input:
            user_input = input(f"You (press new line to finish): ")
            # Audio only needed for TTS playback in CLI mode; skip init entirely if bot_voice is off.
            audio = Audio(self.config) if self.config.bot_voice else None
        else:
            audio = Audio(self.config)
            if audio.audio is None:
                raise RuntimeError("Audio hardware not available. Restart with --cli for text-only mode.")
            audio.init_recording()
            user_input = self.ai.transcribe_and_translate()
            print(f"You: {user_input}")

        route = self.ai.define_route(
            user_input,
            extra_routes=build_extra_routes_text(self._plugin_manifests, location=self.config.location),
        )

        # Plan 08 Phase 2 (default route only): stream LLM response and start TTS playback early.
        can_stream_default = (
            self.config.bot_voice and
            getattr(self.config, "stream_responses", False) and
            getattr(self.config, "stream_tts", False) and
            (route.get("route") not in self.plugins)
        )

        if can_stream_default:
            # stop_event: interrupt playback now (used for playback failures / fatal streaming errors)
            stop_event = threading.Event()
            # production_failed_event: stop producing new streaming audio (but allow already-queued audio to finish)
            production_failed_event = threading.Event()
            stream_tts_buffer_chunks = 2
            text_queue = queue.Queue(maxsize=stream_tts_buffer_chunks)

            # Bound audio queue to avoid unbounded temp-file growth if TTS outpaces playback.
            # Each text chunk can map to 1+ audio files (depending on TTS chunking), so keep this
            # a little larger than the text buffer.
            audio_queue_max_files = max(4, stream_tts_buffer_chunks * 4)
            audio_queue = queue.Queue(maxsize=audio_queue_max_files)

            tts_error = [""]

            # Bound queue-put loops so we don't spin forever if the worker dies/hangs.
            queue_put_max_wait_s = 10.0

            def _put_text_queue(item, allow_when_stopped=False):
                deadline = time.monotonic() + queue_put_max_wait_s
                while True:
                    if stop_event.is_set() and not allow_when_stopped:
                        return False
                    try:
                        text_queue.put(item, timeout=0.1)
                        return True
                    except queue.Full:
                        if time.monotonic() >= deadline:
                            logger.warning("Timed out enqueueing streaming text chunk")
                            return False

            def tts_worker():
                try:
                    while not stop_event.is_set():
                        if production_failed_event.is_set():
                            break
                        try:
                            chunk = text_queue.get(timeout=0.1)
                        except queue.Empty:
                            continue
                        if chunk is None:
                            break
                        tts_files = self.ai.text_to_speech(chunk)

                        if not tts_files:
                            production_failed_event.set()
                            if not tts_error[0]:
                                tts_error[0] = "TTS returned no audio files"
                            break

                        last_idx = -1
                        for idx, f in enumerate(tts_files):
                            last_idx = idx
                            if stop_event.is_set():
                                # Player may have already stopped/drained the queue; delete to avoid leaking temp files.
                                try:
                                    if os.path.exists(f):
                                        os.remove(f)
                                except OSError:
                                    pass
                                continue

                            if production_failed_event.is_set():
                                break

                            deadline = time.monotonic() + queue_put_max_wait_s
                            while not stop_event.is_set():
                                try:
                                    audio_queue.put(f, timeout=0.1)
                                    break
                                except queue.Full:
                                    if time.monotonic() >= deadline:
                                        # Apply backpressure failure path: stop and clean up this file.
                                        production_failed_event.set()
                                        if not tts_error[0]:
                                            tts_error[0] = "Timed out enqueueing streaming audio chunk"
                                        try:
                                            if os.path.exists(f):
                                                os.remove(f)
                                        except OSError:
                                            pass
                                        break

                            if production_failed_event.is_set():
                                break

                        # If we failed mid-chunk, delete any remaining chunk files that were generated but not enqueued.
                        if production_failed_event.is_set() and last_idx != -1 and last_idx < (len(tts_files) - 1):
                            for remaining_file in tts_files[last_idx + 1:]:
                                try:
                                    if os.path.exists(remaining_file):
                                        os.remove(remaining_file)
                                except OSError:
                                    pass

                        if production_failed_event.is_set():
                            break
                finally:
                    # Best-effort: notify player to exit; if the queue is stuck full, force stop_event.
                    try:
                        audio_queue.put(None, timeout=0.1)
                    except queue.Full:
                        stop_event.set()

            player_success = [True]
            player_failed_file = [""]
            player_error = [""]

            def player_worker():
                # Pass the lock so it is acquired per-file, not across the
                # entire queue-drain loop (which blocks on queue.get() between files).
                success, failed_file, error = audio.play_audio_queue(
                    audio_queue, stop_event=stop_event, playback_lock=self._ai_audio_lock
                )
                player_success[0] = bool(success)
                if failed_file:
                    player_failed_file[0] = str(failed_file)
                if error:
                    player_error[0] = str(error)
                if not success:
                    stop_event.set()

            # Use daemon threads so unexpected main-thread exits don't hang shutdown.
            tts_thread = threading.Thread(target=tts_worker, name="stream-tts-worker", daemon=True)
            player_thread = threading.Thread(target=player_worker, name="stream-audio-player", daemon=True)
            tts_thread.start()
            player_thread.start()
            try:

                boundary = str(getattr(self.config, "stream_tts_boundary", "sentence") or "sentence").strip().lower()
                # Rough heuristic for English: ~35 characters/sec spoken.
                chars_per_second = 35
                target_s = 6
                first_min_chars = max(120, int(target_s * chars_per_second))
                next_min_chars = 200

                buffer = ""
                full_parts = []
                is_first = True

                if self.config.debug:
                    print(f"{self.config.botname}: ", end="", flush=True)

                try:
                    for delta in self.ai.stream_response_deltas(user_input):
                        full_parts.append(delta)
                        if stop_event.is_set():
                            # Voice path is interrupted (e.g. TTS/playback failure). Keep collecting deltas
                            # so we can still print the final response text.
                            continue

                        # If TTS production failed, keep collecting deltas for final text output,
                        # but stop producing new audio chunks.
                        if production_failed_event.is_set():
                            continue

                        buffer += delta
                        while not stop_event.is_set():
                            min_chars = first_min_chars if is_first else next_min_chars
                            chunk, buffer = pop_streaming_chunk(buffer, boundary=boundary, min_chars=min_chars)
                            if chunk is None:
                                break
                            is_first = False

                            # Enqueue chunk for TTS generation, respecting backpressure.
                            if not _put_text_queue(chunk):
                                stop_event.set()
                                break
                except Exception as e:
                    stop_event.set()
                    if self.config.debug:
                        # Ensure the error message starts on a new line, separate from streamed output.
                        print()
                    print(handle_api_error(e, service_name="OpenAI GPT (streaming)"))

                # Flush remaining text as final chunk (best effort)
                if (not stop_event.is_set()) and (not production_failed_event.is_set()):
                    final_chunk = buffer.strip()
                    if final_chunk:
                        if not _put_text_queue(final_chunk):
                            stop_event.set()

                # Signal TTS worker completion
                # Ensure the sentinel is eventually enqueued so the TTS worker can exit.
                # Even if stop_event is set, we still try to enqueue the sentinel to unblock.
                sentinel_enqueued = _put_text_queue(None, allow_when_stopped=True)
                if not sentinel_enqueued:
                    # If the queue is stuck full (e.g., hung/slow TTS worker), force an exit path.
                    stop_event.set()
                    logger.warning("Failed to enqueue streaming TTS sentinel; forcing stop_event")

                # Wait for threads to finish playback.
                tts_join_timeout = 30
                player_join_timeout = 60
                tts_thread.join(timeout=tts_join_timeout)
                player_thread.join(timeout=player_join_timeout)
            except Exception:
                stop_event.set()
                raise

            if tts_thread.is_alive() or player_thread.is_alive():
                logger.warning("Streaming TTS threads did not exit cleanly within timeout")

            if not player_success[0]:
                logger.warning("Streaming audio playback failed for '%s': %s", player_failed_file[0], player_error[0])
                print("Audio playback failed during streaming. Continuing with text only.")

            response = "".join(full_parts)
            if not self.config.debug:
                print(f"{self.config.botname}: {response}\n")

            if production_failed_event.is_set() and tts_error[0]:
                logger.warning("Streaming TTS production failed; error: %s", tts_error[0])

            if stop_event.is_set() and tts_error[0]:
                logger.warning("Streaming TTS failed; error: %s", tts_error[0])

        else:
            response = self.route_message(user_input, route)
            print(f"{self.config.botname}: {response}\n")

            if self.config.bot_voice:
                tts_files = self.ai.text_to_speech(response)
                if not tts_files:
                    response_str = "" if response is None else str(response)
                    if response_str.strip():
                        logger.warning("TTS returned no audio files for non-empty response; skipping playback")
                else:
                    with self._ai_audio_lock:
                        success, failed_file, error = audio.play_audio_files(tts_files)
                    if not success:
                        logger.warning("Audio playback failed for '%s': %s", failed_file, error)
                        print("Audio playback failed. Continuing with text only.")
                        if self.config.debug:
                            print(f"Preserving TTS file '{failed_file}' for debugging.")

        if self.config.push_to_talk and not self.config.cli_input:
            input("Press any key to speak...")

if __name__ == "__main__":
    sandvoice = SandVoice()

    if sandvoice.scheduler:
        sandvoice.scheduler.start()

    def _shutdown(signum, frame):
        if sandvoice.scheduler:
            # Signal the scheduler to stop without blocking in the signal handler.
            # The scheduler thread is a daemon; it will be cleaned up at process exit.
            sandvoice.scheduler.stop(timeout=0)
        if signum == signal.SIGINT:
            # Raise KeyboardInterrupt so existing handlers (e.g. WakeWordMode) still work.
            signal.default_int_handler(signum, frame)
        else:
            sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # atexit handlers run LIFO: register cache first so it closes last,
    # after the scheduler thread has already stopped.
    if sandvoice.cache:
        atexit.register(sandvoice.cache.close)

    if sandvoice.scheduler:
        # On normal interpreter exit (including after sys.exit()), join the
        # scheduler thread and close the DB so in-flight writes are not cut short.
        atexit.register(sandvoice.scheduler.close)

    # Wake word mode: hands-free voice activation
    if sandvoice.args.wake_word:
        try:
            from common.wake_word import WakeWordMode
        except ImportError as e:
            print("Error: Wake word mode failed to import one or more required packages.")
            print("Please ensure all project dependencies are installed (e.g., 'pip install -r requirements.txt'),")
            print("including pvporcupine==4.0.1, webrtcvad==2.0.10, and PyAudio. Details:")
            print(f"  {e}")
            sys.exit(1)

        from common.terminal_ui import TerminalUI
        audio = Audio(sandvoice.config)
        ui = (
            TerminalUI(wake_phrase=sandvoice.config.wake_phrase)
            if sandvoice.config.visual_state_indicator
            else None
        )
        wake_word_mode = WakeWordMode(
            sandvoice.config,
            sandvoice.ai,
            audio,
            route_message=sandvoice.route_message,
            plugins=sandvoice.plugins,
            audio_lock=sandvoice._ai_audio_lock,
            cache=sandvoice.cache,
            ui=ui,
            extra_routes=build_extra_routes_text(
                sandvoice._plugin_manifests, location=sandvoice.config.location
            ),
        )
        wake_word_mode.run()
    # Default mode (ESC key) or CLI mode
    else:
        while True:
            logger.debug("Conversation history: %s", sandvoice.ai.conversation_history)
            logger.debug("SandVoice: %s", sandvoice)
            try:
                sandvoice.runIt()
            except RuntimeError as e:
                sys.exit(str(e))

## TODO
# Add some tests
# Have proper error checking in multiple parts of the code
# Add temperature forecast for a week or close days
# Launch summaries in parallel
# have specific configuration files for each plugin
# break the routes.yaml into sections
# statistics on how long the session took
# Make realtime be able to read pdf (from url)
# read all roles from yaml files
# write history on a file
# fix history by removing control messages
# make the audio files randomly created and removed, to support multiple uses at the same time
# make the system role overridable
# add support to send messages when there's a silence for N seconds in the input audio
