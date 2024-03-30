from common.configuration import Config
from common.audio import Audio
from openai import OpenAI
from jinja2 import Template
import os, datetime, json, yaml, warnings, importlib

class SandVoice:
    def __init__(self):
        self.openai_client = OpenAI()
        self.is_recording = False
        self.conversation_history = []
        self.config = Config()

        if not os.path.exists(self.config.tmp_files_path):
            os.makedirs(self.config.tmp_files_path)
        self.plugins = {}
        self.load_plugins()

    def load_plugins(self):
        plugins_dir = "plugins"
        for filename in os.listdir(plugins_dir):
            if filename.endswith(".py"):
                module_name = os.path.splitext(filename)[0]
                module = importlib.import_module(f"plugins.{module_name}")

                # Expect a class named 'Plugin' or a top-level 'process' function
                if hasattr(module, 'Plugin'):
                    self.plugins[module_name] = module.Plugin()
                elif hasattr(module, 'process'):
                    self.plugins[module_name] = module.process

    def transcribe_and_translate(self):
        with open(self.config.tmp_recording + ".mp3", "rb") as file:
            transcript = self.openai_client.audio.translations.create(
                model="whisper-1",
                file=file
            )
        return transcript.text

    def generate_response(self, user_input, extra_info = None):
        try:
            self.conversation_history.append("User: " + user_input)
            now = datetime.datetime.now()
            system_role = f"""
            Your name is {self.config.botname}.
            Your are an assisten written in Python by Breno Brand.
            You Answer must be in {self.config.language}.
            The person that is talking to you is in the {self.config.timezone} time zone.
            The person that is talking to you is located in {self.config.location}.
            Right now it is {now}.
            Never answer as a chat, for example reading your name in a conversation.
            DO NOT reply to messages with the format "{self.config.botname}": <message here>.
            Reply in a natural and human way.
            """
            if extra_info != None:
                system_role = system_role + "Consider the following to answer your question: " + extra_info
                if self.config.debug:
                    print (system_role)
            # Be very sympathetic, helpful and don't be rude or have short answers"

            completion = self.openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_role},
                ] + [{"role": "user", "content": message} for message in self.conversation_history]
            )
            self.conversation_history.append(f"{self.config.botname}: " + completion.choices[0].message.content)
            return completion.choices[0].message
        except Exception as e:
            print("A general error occurred:", e)
            return "Sorry, I'm having trouble thinking right now. Could you try again later?"

    def define_route(self, user_input):
        try:
            with open('./routes.yaml', 'r') as f:
                template_str = f.read()
            template = Template(template_str)
            rendered_config = template.render(location=self.config.location)
            system_role = yaml.safe_load(rendered_config)

            completion = self.openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            # model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": system_role['route_role']},
                {"role": "user", "content": user_input}
            ])
            return json.loads(completion.choices[0].message.content)
        except Exception as e:
            print("A general error occurred:", e)
            return "Sorry, I'm having trouble thinking right now. Could you try again later?"

    def text_summary(self, user_input, extra_info = None, words = "100"):
        try:
            if self.config.debug:
                print("Summary words: " + words)
                print("Before: " + user_input)
            system_role = f"""
            You're a bot summaries texts in {words} words.
            If there is a date of the text you are reading, mention the date in the summary.
            The summary must content the most important information of the text.
            Your answer will be in json format: {{"title": "some title", "text": "the summary here"}}.
            The text must be translated to {self.config.language} if required.
            If one of the texts has no content or has an error, figure something out from the title.
            You will receive a text and you need to summarize it in {words} words and return the title and the summary.
            You must be able to answer the user's question with the summary. For example, if the user is asking for a recipe, your answer must have the recipe.
            The only condition that will allow you bypass the limite of {words} words is if that amount of words is not enough to summarize the text.
            Do your best to be as close to the limit  of {words} words as possible.
            """

            if self.config.debug:
                print(system_role)
            if extra_info != None:
                system_role = "Consider that this is the question of the user: {extra_info}" + system_role

            completion = self.openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_role},
                {"role": "user", "content": user_input}
            ])
            if self.config.debug:
                print("After: " +completion.choices[0].message.content + "\n")
            return json.loads(completion.choices[0].message.content)
        except Exception as e:
            print("A general error occurred:", e)
            return "None"

    def text_to_speech(self, text):
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        speech_file_path = self.config.tmp_recording + ".mp3"
        response = self.openai_client.audio.speech.create(
            model="tts-1",
            voice="nova",
            input=text
        )
        response.stream_to_file(speech_file_path)

    def route_message(self, user_input):
        route = self.define_route(user_input)
        if self.config.debug:
            print(route)
            print(f"Plugins: {str(self.plugins)}")
        if route["route"] in self.plugins:
            return self.plugins[route["route"]](user_input, route, self)
        else:
            return self.generate_response(user_input).content

    def runIt(self):
        self.audio = Audio(self.config)

        user_input = self.transcribe_and_translate()
        print(f"\nUser: {user_input}")

        response = self.route_message(user_input)
        print(f"{self.config.botname}: {response}\n")

        if self.config.botvoice:
            self.text_to_speech(response)
            self.audio.play_audio()

        if self.config.push_to_talk:
            input("Press any key to speak...")

if __name__ == "__main__":
    sandvoice = SandVoice()
    while True:
        if sandvoice.config.debug:
            print(sandvoice.conversation_history)
            print(sandvoice.__str__())
        sandvoice.runIt()

## TODO
# Separate the bot AI/messaging in a separate class
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