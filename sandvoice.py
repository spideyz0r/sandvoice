import os, datetime, json, sys, re, warnings, importlib
from ctypes import *
import pyaudio
import wave
from pynput import keyboard
import lameenc
from openai import OpenAI
# this is necessary to mute some outputs from pygame
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame
import yaml
from jinja2 import Template

class Config:
    def __init__(self):
        self.config_file = f"{os.environ['HOME']}/.sandvoice/config.yaml"
        self.defaults  = {
            "channels": 2,
            "bitrate": 128,
            "rate": 44100,
            "chunk": 1024,
            "tmp_files_path": f"{os.environ['HOME']}/.sandvoice/tmp/",
            "botname": "SandVoice",
            "timezone": "EST",
            "location": "Toronto, ON, CA",
            "language": "English",
            "debug": "disabled",
            "summary_words": "100",
            "search_sources": "4",
            "push_to_talk": "disabled",
            "rss_news": "https://feeds.bbci.co.uk/news/rss.xml",
            "rss_news_max_items": "5",
            "linux_warnings": "enabled",
            "botvoice": "enabled"
        }
        self.config = self.load_config()

    def load_config(self):
        if not os.path.exists(self.config_file):
            return self.defaults
        with open(self.config_file, "r") as f:
            data = yaml.safe_load(f)
        # combine both dicts, data overrides defaults
        return {**self.defaults, **data}

    def get(self, key):
            return self.config.get(key, self.defaults[key])

class SandVoice:
    def __init__(self):
        self.format = pyaudio.paInt16
        self.openai_client = OpenAI()
        self.is_recording = False
        self.conversation_history = []
        config = Config()
        self.channels = config.get("channels")
        self.bitrate = config.get("bitrate")
        self.rate = config.get("rate")
        self.chunk = config.get("chunk")
        self.tmp_files_path = config.get("tmp_files_path")
        self.botname = config.get("botname")
        self.timezone = config.get("timezone")
        self.location = config.get("location")
        self.language = config.get("language")
        self.summary_words = config.get("summary_words")
        self.search_sources = config.get("search_sources")
        self.rss_news = config.get("rss_news")
        self.rss_news_max_items = config.get("rss_news_max_items")
        self.tmp_recording = self.tmp_files_path + "recording"
        self.debug = config.get("debug").lower() == "enabled"
        self.botvoice = config.get("botvoice").lower() == "enabled"
        self.push_to_talk = config.get("push_to_talk").lower() == "enabled"
        self.linux_warnings = config.get("linux_warnings").lower() == "enabled"
        if not os.path.exists(self.tmp_files_path):
            os.makedirs(self.tmp_files_path)
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

    def on_press(self, key):
        if key == keyboard.Key.esc:
            self.is_recording = False

    def stop_recording(self):
        self.is_recording = False

    def start_recording(self):
        self.is_recording = True
        print(">> Listening... press ^ to stop")
        stream = self.audio.open(format=self.format, channels=self.channels,
                            rate=self.rate, input=True,
                            frames_per_buffer=self.chunk)
        frames = []

        while self.is_recording:
            data = stream.read(self.chunk)
            frames.append(data)

        stream.stop_stream()
        stream.close()
        if self.debug:
            print("Recording stopped.")

        wf = wave.open(self.tmp_recording + ".wav", 'wb')
        wf.setnchannels(self.channels)
        wf.setsampwidth(self.audio.get_sample_size(self.format))
        wf.setframerate(self.rate)
        wf.writeframes(b''.join(frames))
        wf.close()
        self.audio.terminate()

    def convert_to_mp3(self):
        lame = lameenc.Encoder()
        lame.set_bit_rate(self.bitrate)
        lame.set_in_sample_rate(self.rate)
        lame.set_channels(self.channels)
        lame.set_quality(self.channels)
        with open(self.tmp_recording + ".wav", "rb") as wav_file, open(self.tmp_recording + ".mp3", "wb") as mp3_file:
            mp3_data = lame.encode(wav_file.read())
            mp3_file.write(mp3_data)

    def transcribe_and_translate(self):
        with open(self.tmp_recording + ".mp3", "rb") as file:
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
            Your name is {self.botname}.
            Your are an assisten written in Python by Breno Brand.
            You Answer must be in {self.language}.
            The person that is talking to you is in the {self.timezone} time zone.
            The person that is talking to you is located in {self.location}.
            Right now it is {now}.
            Never answer as a chat, for example reading your name in a conversation.
            DO NOT reply to messages with the format "{self.botname}": <message here>.
            Reply in a natural and human way.
            """
            if extra_info != None:
                system_role = system_role + "Consider the following to answer your question: " + extra_info
                if self.debug:
                    print (system_role)
            # Be very sympathetic, helpful and don't be rude or have short answers"

            completion = self.openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_role},
                ] + [{"role": "user", "content": message} for message in self.conversation_history]
            )
            self.conversation_history.append(f"{self.botname}: " + completion.choices[0].message.content)
            return completion.choices[0].message
        except Exception as e:
            print("A general error occurred:", e)
            return "Sorry, I'm having trouble thinking right now. Could you try again later?"

    def define_route(self, user_input):
        try:
            with open('./routes.yaml', 'r') as f:
                template_str = f.read()
            if self.debug:
                print(template_str)
            template = Template(template_str)
            rendered_config = template.render(location=self.location)
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
            if self.debug:
                print("Summary words: " + words)
                print("Before: " + user_input)
            system_role = f"""
            You're a bot summaries texts in {words} words.
            If there is a date of the text you are reading, mention the date in the summary.
            The summary must content the most important information of the text.
            Your answer will be in json format: {{"title": "some title", "text": "the summary here"}}.
            The text must be translated to {self.language} if required.
            If one of the texts has no content or has an error, figure something out from the title.
            You will receive a text and you need to summarize it in {words} words and return the title and the summary.
            """

            if self.debug:
                print(system_role)
            if extra_info != None:
                system_role = "Consider that this is the question of the user: {extra_info}" + system_role

            completion = self.openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_role},
                {"role": "user", "content": user_input}
            ])
            if self.debug:
                print("After: " +completion.choices[0].message.content + "\n")
            return json.loads(completion.choices[0].message.content)
        except Exception as e:
            print("A general error occurred:", e)
            return "None"

    def text_to_speech(self, text):
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        speech_file_path = self.tmp_recording + ".mp3"
        response = self.openai_client.audio.speech.create(
            model="tts-1",
            voice="nova",
            input=text
        )
        response.stream_to_file(speech_file_path)

    def play_audio(self):
        pygame.mixer.init()
        pygame.mixer.music.load(self.tmp_recording + ".mp3")
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)

    def route_message(self, user_input):
        route = self.define_route(user_input)
        if self.debug:
            print(route)
            print(f"Plugins: {str(self.plugins)}")
        if route["route"] in self.plugins:
            return self.plugins[route["route"]](user_input, route, self)
        else:
            return self.generate_response(user_input).content

    def get_libasound_path(self):
        lib_paths = [
            '/usr/lib',
            '/usr/lib64',
            '/lib',
            '/lib64',
        ]
        lib_pattern = re.compile(r'libasound\.so\..*')
        for file in lib_paths:
            if not os.path.isdir(file):
                continue
            for f in os.listdir(file):
                if lib_pattern.match(f):
                    return f
        return None

    def initialize_audio(self):
        if not self.linux_warnings:
            ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)
            c_error_handler = ERROR_HANDLER_FUNC(self.py_error_handler)
            f = self.get_libasound_path()
            if self.debug:
                print("Loading libasound from: " + f)
            asound = cdll.LoadLibrary(f)
            asound.snd_lib_error_set_handler(c_error_handler)
        self.audio = pyaudio.PyAudio()

    def py_error_handler(self, filename, line, function, err, fmt):
        pass

    def runIt(self):
        self.initialize_audio()

        listener = keyboard.Listener(on_press=sandvoice.on_press)
        listener.start()

        self.start_recording()
        self.convert_to_mp3()

        user_input = self.transcribe_and_translate()
        print(f"\nUser: {user_input}")

        response = self.route_message(user_input)

        print(f"{self.botname}: {response}\n")
        if self.botvoice:
            self.text_to_speech(response)
            self.play_audio()
        if self.push_to_talk:
            input("Press any key to speak...")

if __name__ == "__main__":
    sandvoice = SandVoice()
    while True:
        if sandvoice.debug:
            print(sandvoice.conversation_history)
            print(sandvoice.__str__())
        sandvoice.runIt()

## TODO
# After getting the first response, have the option to press a key before start recording again
# Separate the bot AI/messaging in a separate class
# A class for audio handling
# Add some tests
# Have proper error checking in multiple parts of the code
# Add temperature forecast for a week or close days
# Launch summarines in parallel
# Read models from config file
# have specific configuration files for each plugin
# break the routes.yaml into sections
# have the option to input with command line
# statistics on how long the session took