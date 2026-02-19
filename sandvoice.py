#!/usr/bin/env python3
import warnings
# Suppress pygame's pkg_resources deprecation warning (pygame issue, not ours)
warnings.filterwarnings("ignore", message="pkg_resources is deprecated")

from common.configuration import Config
from common.audio import Audio
from common.ai import AI, pop_streaming_chunk
from common.error_handling import handle_api_error

import argparse, importlib, os, sys
import queue, threading

class SandVoice:
    def __init__(self):
        self.parse_args()
        self.config = Config()
        self.ai = AI(self.config)
        if not os.path.exists(self.config.tmp_files_path):
            os.makedirs(self.config.tmp_files_path)
        self.plugins = {}
        self.load_plugins()
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
            stop_event = threading.Event()
            text_queue = queue.Queue(maxsize=max(1, int(getattr(self.config, "stream_tts_buffer_chunks", 2) or 2)))
            audio_queue = queue.Queue()

            tts_error = [""]

            def tts_worker():
                try:
                    while not stop_event.is_set():
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
                            stop_event.set()
                            if not tts_error[0]:
                                tts_error[0] = "TTS returned no audio files"
                            break

                        for f in tts_files:
                            audio_queue.put(f)
                finally:
                    audio_queue.put(None)

            def player_worker():
                return audio.play_audio_queue(audio_queue, stop_event=stop_event)

            tts_thread = threading.Thread(target=tts_worker, name="stream-tts-worker")
            player_thread = threading.Thread(target=player_worker, name="stream-audio-player")
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
                        continue

                    buffer += delta
                    while not stop_event.is_set():
                        min_chars = first_min_chars if is_first else next_min_chars
                        chunk, buffer = pop_streaming_chunk(buffer, boundary=boundary, min_chars=min_chars)
                        if chunk is None:
                            break
                        is_first = False

                        # Enqueue chunk for TTS generation, respecting backpressure.
                        while not stop_event.is_set():
                            try:
                                text_queue.put(chunk, timeout=0.1)
                                break
                            except queue.Full:
                                continue
            except Exception as e:
                stop_event.set()
                print(handle_api_error(e, service_name="OpenAI GPT (streaming)"))

            # Flush remaining text as final chunk (best effort)
            if not stop_event.is_set():
                final_chunk = buffer.strip()
                if final_chunk:
                    while not stop_event.is_set():
                        try:
                            text_queue.put(final_chunk, timeout=0.1)
                            break
                        except queue.Full:
                            continue

            # Signal TTS worker completion
            if not stop_event.is_set():
                try:
                    text_queue.put(None, timeout=0.1)
                except queue.Full:
                    # Best-effort: if queue is full, worker will still exit after draining.
                    pass
            else:
                # Best-effort: unblock worker if it is waiting.
                try:
                    text_queue.put(None, timeout=0.1)
                except Exception:
                    pass

            # Ensure newline when printing deltas
            if self.config.debug and stream_print_deltas:
                print("\n", flush=True)

            # Wait for threads to finish playback.
            tts_thread.join(timeout=30)
            player_thread.join(timeout=60)

            if (tts_thread.is_alive() or player_thread.is_alive()) and self.config.debug:
                print("Warning: streaming TTS threads did not exit cleanly within timeout")

            response = "".join(full_parts)
            if not (self.config.debug and stream_print_deltas):
                print(f"{self.config.botname}: {response}\n")

            if stop_event.is_set() and tts_error[0]:
                if self.config.debug:
                    print(f"Streaming TTS failed; continuing with text only. Error: {tts_error[0]}")

        else:
            response = self.route_message(user_input, route)
            print(f"{self.config.botname}: {response}\n")

            if self.config.bot_voice:
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
