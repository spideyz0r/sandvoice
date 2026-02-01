#!/usr/bin/env python3
from common.configuration import Config
from common.audio import Audio
from common.ai import AI
from common.wake_word import WakeWordMode

import argparse, importlib, os

class SandVoice:
    def __init__(self):
        self.config = Config()
        self.ai = AI(self.config)
        if not os.path.exists(self.config.tmp_files_path):
            os.makedirs(self.config.tmp_files_path)
        self.plugins = {}
        self.load_plugins()
        self.load_cli()
        if self.args.cli:
            self.config.cli_input = True

    def load_cli(self):
        self.parser = argparse.ArgumentParser(
            description='Cli mode for SandVoice'
        )

        self.parser.add_argument(
            '--cli',
            action='store_true',
            help='enter cli mode (equivalent to yaml option cli_input: enabled)'
        )
        self.parser.add_argument(
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
        audio = Audio(sandvoice.config)
        wake_word_mode = WakeWordMode(sandvoice.config, sandvoice.ai, audio)
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
