#!/usr/bin/env python3
import warnings
# Suppress pygame's pkg_resources deprecation warning (pygame issue, not ours)
warnings.filterwarnings("ignore", message="pkg_resources is deprecated")

from common.configuration import Config
from common.audio import Audio
from common.ai import AI, pop_streaming_chunk
from common.error_handling import handle_api_error
from common.db import SchedulerDB
from common.scheduler import TaskScheduler

import argparse, importlib, os, signal, sys
import queue, threading, time

class SandVoice:
    def __init__(self):
        self.parse_args()
        self.config = Config()
        self.ai = AI(self.config)
        if not os.path.exists(self.config.tmp_files_path):
            os.makedirs(self.config.tmp_files_path)
        self.plugins = {}
        self.load_plugins()
        self._ai_audio_lock = threading.Lock()
        self._scheduler_audio = None  # lazily created on first scheduler voice task
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
        if self.config.debug:
            print(f"Loading plugins from {self.config.plugin_path}")
        plugins_dir = self.config.plugin_path
        for filename in os.listdir(plugins_dir):
            if filename.endswith(".py"):
                try:
                    module_name = os.path.splitext(filename)[0]
                    module = importlib.import_module(f"plugins.{module_name}")
                except Exception as e:
                    print(f"Error loading plugin {filename}: {e}")
                    continue

                # Expect a class named 'Plugin' or a top-level 'process' function
                if hasattr(module, 'Plugin'):
                    self.plugins[module_name] = module.Plugin()
                elif hasattr(module, 'process'):
                    self.plugins[module_name] = module.process

    def _init_scheduler(self):
        if not self.config.scheduler_enabled:
            return None
        try:
            self._scheduler_ai = AI(self.config)
            db = SchedulerDB(self.config.scheduler_db_path)
            return TaskScheduler(
                db=db,
                speak_fn=self._scheduler_speak,
                invoke_plugin_fn=self._scheduler_invoke_plugin,
                poll_interval_s=self.config.scheduler_poll_interval,
            )
        except Exception as e:
            print(f"Warning: scheduler disabled — failed to initialize: {e}")
            return None

    def _scheduler_speak(self, text):
        if not text or not self.config.bot_voice:
            return
        with self._ai_audio_lock:
            if self._scheduler_audio is None:
                self._scheduler_audio = Audio(self.config)
            tts_files = self.ai.text_to_speech(text)
            if tts_files:
                self._scheduler_audio.play_audio_files(tts_files)

    def _scheduler_invoke_plugin(self, plugin_name, query, refresh_only):
        with self._ai_audio_lock:
            route = {"route": plugin_name}
            result = self._scheduler_route_message(query or plugin_name, route)
            if not refresh_only and self.config.bot_voice and result:
                if self._scheduler_audio is None:
                    self._scheduler_audio = Audio(self.config)
                tts_files = self.ai.text_to_speech(result)
                if tts_files:
                    self._scheduler_audio.play_audio_files(tts_files)
        return result

    def _scheduler_route_message(self, user_input, route):
        """Route a scheduler-triggered message using a dedicated AI instance to avoid
        polluting the interactive conversation history."""
        if self.config.debug:
            print(route)
            print(f"Plugins: {str(self.plugins)}")
        if route["route"] in self.plugins:
            return self.plugins[route["route"]](user_input, route, self)
        else:
            return self._scheduler_ai.generate_response(user_input).content

    def route_message(self, user_input, route):
        if self.config.debug:
            print(route)
            print(f"Plugins: {str(self.plugins)}")
        if route["route"] in self.plugins:
            return self.plugins[route["route"]](user_input, route, self)
        else:
            return self.ai.generate_response(user_input).content

    def runIt(self):
        audio = Audio(self.config)
        if self.config.cli_input:
            user_input = input(f"You (press new line to finish): ")
        else:
            audio.init_recording()
            user_input = self.ai.transcribe_and_translate()
            print(f"You: {user_input}")

        route = self.ai.define_route(user_input)

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
            stream_tts_buffer_chunks = max(1, int(getattr(self.config, "stream_tts_buffer_chunks", 2) or 2))
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
                            if self.config.debug:
                                print("Warning: timed out enqueueing streaming text chunk")
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
                        try:
                            tts_files = self.ai.text_to_speech(chunk)
                        except Exception as e:
                            tts_files = []
                            tts_error[0] = str(e)

                        if not tts_files:
                            production_failed_event.set()
                            # Preserve the first error (if any) from text_to_speech.
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
                success, failed_file, error = audio.play_audio_queue(audio_queue, stop_event=stop_event)
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
            # Serialize with scheduler audio to prevent pygame mixer contention
            # while streaming TTS worker and player threads are active.
            self._ai_audio_lock.acquire()
            try:
                tts_thread.start()
                player_thread.start()

                boundary = str(getattr(self.config, "stream_tts_boundary", "sentence") or "sentence").strip().lower()
                try:
                    target_s = int(getattr(self.config, "stream_tts_first_chunk_target_s", 6) or 6)
                except Exception:
                    target_s = 6

                # Rough heuristic for English: ~35 characters/sec spoken.
                chars_per_second = 35
                first_min_chars = max(120, int(target_s * chars_per_second))
                next_min_chars = 200

                stream_print_deltas = bool(getattr(self.config, "stream_print_deltas", False))

                buffer = ""
                full_parts = []
                is_first = True

                if self.config.debug and stream_print_deltas:
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
                    if self.config.debug and stream_print_deltas:
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
                    if self.config.debug:
                        print("Warning: failed to enqueue streaming TTS sentinel; forcing stop_event")

                # Wait for threads to finish playback.
                tts_join_timeout = int(getattr(self.config, "stream_tts_tts_join_timeout_s", 30) or 30)
                player_join_timeout = int(getattr(self.config, "stream_tts_player_join_timeout_s", 60) or 60)
                tts_thread.join(timeout=tts_join_timeout)
                player_thread.join(timeout=player_join_timeout)
            finally:
                self._ai_audio_lock.release()

            if (tts_thread.is_alive() or player_thread.is_alive()) and self.config.debug:
                print("Warning: streaming TTS threads did not exit cleanly within timeout")

            if not player_success[0]:
                if self.config.debug:
                    print(
                        f"Error during streaming audio playback for file '{player_failed_file[0]}': {player_error[0]}\n"
                        "Stopping voice playback and continuing with text only."
                    )
                else:
                    print("Audio playback failed during streaming. Continuing with text only.")

            response = "".join(full_parts)
            if not (self.config.debug and stream_print_deltas):
                print(f"{self.config.botname}: {response}\n")

            if production_failed_event.is_set() and tts_error[0] and self.config.debug:
                print(
                    "Streaming TTS production failed; finishing playback of already-queued audio and continuing with text only. "
                    f"Error: {tts_error[0]}"
                )

            if stop_event.is_set() and tts_error[0]:
                if self.config.debug:
                    print(f"Streaming TTS failed; continuing with text only. Error: {tts_error[0]}")

        else:
            response = self.route_message(user_input, route)
            print(f"{self.config.botname}: {response}\n")

            if self.config.bot_voice:
                with self._ai_audio_lock:
                    tts_files = self.ai.text_to_speech(response)
                    if not tts_files:
                        if self.config.debug:
                            response_str = "" if response is None else str(response)
                            if not response_str.strip():
                                print("TTS was requested (bot_voice enabled) but response text was empty; skipping audio playback.")
                            else:
                                print(
                                    "TTS was requested (bot_voice enabled) for a non-empty response, "
                                    "but no audio files were generated. This may indicate that the TTS API failed, "
                                    "that the response text was filtered out as empty/whitespace during preprocessing, "
                                    "or another internal TTS issue. Skipping audio playback."
                                )
                    else:
                        success, failed_file, error = audio.play_audio_files(tts_files)
                        if not success:
                            if self.config.debug:
                                print(f"Error during audio playback for file '{failed_file}': {error}")
                                print("Stopping voice playback and continuing with text only.")
                                print(f"Preserving TTS file '{failed_file}' for debugging.")
                            else:
                                print("Audio playback failed. Continuing with text only.")

        if self.config.push_to_talk and not self.config.cli_input:
            input("Press any key to speak...")

if __name__ == "__main__":
    sandvoice = SandVoice()

    if sandvoice.scheduler:
        sandvoice.scheduler.start()

    def _shutdown(signum, frame):
        if sandvoice.scheduler:
            sandvoice.scheduler.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

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

        audio = Audio(sandvoice.config)
        wake_word_mode = WakeWordMode(
            sandvoice.config,
            sandvoice.ai,
            audio,
            route_message=sandvoice.route_message,
            plugins=sandvoice.plugins,
        )
        wake_word_mode.run()
    # Default mode (ESC key) or CLI mode
    else:
        while True:
            if sandvoice.config.debug:
                print(sandvoice.ai.conversation_history)
                print(sandvoice.__str__())
            sandvoice.runIt()

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
