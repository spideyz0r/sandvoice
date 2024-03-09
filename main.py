import os, datetime, json
import pyaudio
import wave
import pynput
from pynput import keyboard
import lameenc
from openai import OpenAI
import warnings
import sounddevice
# this is necessary to mute some outputs from pygame
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame
import requests
import yaml

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

class HackerNews:
    def __init__(self):
        self.base_url = "https://hacker-news.firebaseio.com/v0/"
        self.limit = 5

    def get_best_story_ids(self):
        response = requests.get(self.base_url + "beststories.json")
        return response.json()

    def get_story_details(self, story_id):
        response = requests.get(self.base_url + f"item/{story_id}.json")
        return response.json()

    def get_best_stories(self):
        story_ids = self.get_best_story_ids()[:self.limit]

        stories = []
        for story_id in story_ids:
            story = self.get_story_details(story_id)
            stories.append(f"{story['title']} - {story['url']}")
        return stories

class OpenWeatherReader:
    def __init__(self, location, unit = "metric"):
        self.api_key = os.environ['OPENWEATHERMAP_API_KEY']
        self.location = location
        self.unit = unit
        self.base_url = "https://api.openweathermap.org/data/2.5/weather?"

    def get_current_weather(self):
        url = f"{self.base_url}q={self.location}&appid={self.api_key}&units={self.unit}"
        response = requests.get(url)

        if response.status_code == 200:
            # not formating the output, since the model can understand that
            return response.json()
        else:
            return None

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
        self.tmp_recording = self.tmp_files_path + "recording"
        self.debug = config.get("debug") == "enabled"
        self.botvoice = config.get("botvoice") == "enabled"
        if not os.path.exists(self.tmp_files_path):
            os.makedirs(self.tmp_files_path)

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
            You Answer in {self.language}.
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
            system_role = f"""
            You're a route bot.
            You answer in json in the following format: {{"route": "routename"}}
            The content of "routename" is defined according to the message of the user.
            Based on the message of the user and the description of each route you need to choose the route that best fits.
            Bellow follows each route name and it's description delimited by ":"
            weather: The user is asking how the weather is or feels like, the user may or may not mention what is the location. For example: "How is the weather outside now?"
            news: The user might be asking about real time news. For example: "What are the news today?"
            default: This is the route for when no other route matches.

            Now here are some notes:
            #0 If the route is weather never leave location or unit empty.
            #1 If no location is defined, consider {self.location}.
            #2 Convert the location to the following convention: City name, state code (only for the US) and country code divided by comma. Trim all spaces. Please use ISO 3166 country codes. For example: Toronto,ON,CA.
            #3 If the route is weather, add to the json a key location with the target location, a key unit that if not informed by default is metric.
            """
            completion = self.openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_role},
                {"role": "user", "content": user_input}
            ])
            return json.loads(completion.choices[0].message.content)
        except Exception as e:
            print("A general error occurred:", e)
            return "Sorry, I'm having trouble thinking right now. Could you try again later?"

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
        match route["route"]:
            case "weather":
                if not route.get('location'):
                    self.route_message(user_input)
                weather = OpenWeatherReader(route['location'], route['unit'])
                current_weather = weather.get_current_weather()
                response = self.generate_response(user_input, f"You can answer questions about weather. This is the information of the weather the user asked: {str(current_weather)}\n")
            case "news":
                hacker_news = HackerNews()
                stories = hacker_news.get_best_stories()
                response = self.generate_response(user_input, f"Use this information to answer questions about any news. This is the hot news at Hacker News at the moment: {str(stories)}. Don't read the URLs \n. Use your knowledge to give some context to each new if possible")
            case _:
                response = self.generate_response(user_input)
        return response

    def runIt(self):
        self.audio = pyaudio.PyAudio()

        listener = keyboard.Listener(on_press=sandvoice.on_press)
        listener.start()

        self.start_recording()
        self.convert_to_mp3()

        user_input = self.transcribe_and_translate()
        print(f"\nUser: {user_input}")

        response = self.route_message(user_input)

        print(f"{self.botname}: {response.content}\n")
        if self.botvoice:
            self.text_to_speech(response.content)
            self.play_audio()

if __name__ == "__main__":
    sandvoice = SandVoice()
    while True:
        if sandvoice.debug:
            print(sandvoice.conversation_history)
            print(sandvoice.__str__())
            print(sandvoice.__repr__())
            print(sandvoice)
        sandvoice.runIt()

## TODO
# Use some fancy CLI tooling like cobra
# Read configurations such as language, voice, etc from a file
# Separate the bot messaging in a separate class