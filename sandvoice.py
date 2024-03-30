from common.configuration import Config
from common.audio import Audio
from common.ai import AI

import os, importlib

class SandVoice:
    def __init__(self):
        self.config = Config()
        self.ai = AI(self.config)
        if not os.path.exists(self.config.tmp_files_path):
            os.makedirs(self.config.tmp_files_path)
        self.plugins = {}
        self.load_plugins()

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

    def route_message(self, user_input):
        route = self.ai.define_route(user_input)
        if self.config.debug:
            print(route)
            print(f"Plugins: {str(self.plugins)}")
        if route["route"] in self.plugins:
            return self.plugins[route["route"]](user_input, route, self)
        else:
            return self.ai.generate_response(user_input).content

    def runIt(self):
        audio = Audio(self.config)

        user_input = self.ai.transcribe_and_translate()
        print(f"\nUser: {user_input}")

        response = self.route_message(user_input)
        print(f"{self.config.botname}: {response}\n")

        if self.config.botvoice:
            self.ai.text_to_speech(response)
            audio.play_audio()

        if self.config.push_to_talk:
            input("Press any key to speak...")

if __name__ == "__main__":
    sandvoice = SandVoice()
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
# Read models from config file
# have specific configuration files for each plugin
# break the routes.yaml into sections
# have the option to input with command line
# statistics on how long the session took
# Make realtime be able to read pdf
# read all roles from yaml files

