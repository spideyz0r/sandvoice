import os, datetime, json
import pyaudio
import wave
from pynput import keyboard
import lameenc
from openai import OpenAI
import warnings
# this is necessary to mute some outputs from pygame
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame
import requests
import yaml
from bs4 import BeautifulSoup
from googlesearch import search



class GoogleSearcher:
    def __init__(self, num_results=3):
        self.num_results = num_results

    def search(self, query):
        print (f"Searching for {query}, getting {self.num_results} results.")
        results = search(query, num_results=self.num_results)
        return list(results)

class WebTextExtractor:
    def __init__(self, url):
        self.url = url
        self.headers = {
            "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:106.0) Gecko/20100101 Firefox/106.0",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "CallTreeId": "||BTOC-1BF47A0C-CCDD-47BB-A9DA-592009B5FB38",
            "Content-Type": "application/json; charset=UTF-8",
            "x-timeout-ms": "5000",
            "DNT": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin"
            }

    def remove_non_ascii(self, text):
        return ''.join(char for char in text if ord(char) < 128)

    def get_text(self):
        response = requests.get(self.url, headers=self.headers)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'lxml')
        for script in soup(["script", "style"]):
            script.extract()
        text = soup.get_text()
        text = BeautifulSoup(text, "lxml").text
        text = text.strip().replace("\n", " ").replace("\r", " ").replace("\t", " ")
        cleaned_result = self.remove_non_ascii(text)
        return cleaned_result

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

    def get_best_stories_summary(self):
        summaries = []
        story_ids = self.get_best_story_ids()[:self.limit]
        for story_id in story_ids:
            story = self.get_story_details(story_id)
            extractor = WebTextExtractor(story['url'])
            text = extractor.get_text()
            summaries.append({"title": story['title'], "text": text})
        return summaries

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
        self.summary_words = config.get("summary_words")
        self.search_sources = config.get("search_sources")
        self.tmp_recording = self.tmp_files_path + "recording"
        self.debug = config.get("debug").lower() == "enabled"
        self.botvoice = config.get("botvoice").lower() == "enabled"
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
            system_role = f"""
            You're a route bot.
            You answer must be in json in the following format: {{"route": "routename"}}
            The content of "routename" is defined according to the message of the user.
            Based on the message of the user and the description of each route you need to choose the route that best fits.
            Bellow follows each route name and it's description delimited by ":"

            weather: The user is asking how the weather is or feels like, the user may or may not mention what is the location. For example: "How is the weather outside now?"
            news-summary: The user might be asking about a summary of the real time news. For example: "What are the summary of the news today? Another example: What are the details of the news today?"
            news: The user might be asking about real time news. This is just gonna list the topics For example: "What are the news today? Another example: What are the top 5 news today?"
            other-realtime: This is for any other real time information that is not news or weather. But see if this is potentially something you know, don't use this route. This is a real-time information. For example: "What is the price of Bitcoin today?"
            default: This is the route for when no other route matches.

            Rules for the routes:
            #0 If the route is weather never leave location or unit empty.
            #1 If no location is defined, consider {self.location}.
            #2 Convert the location to the following convention: City name, state code (only for the US) and country code divided by comma. Trim all spaces. Please use ISO 3166 country codes. For example: Toronto,ON,CA.
            #3 If the route is weather, add to the json a key location with the target location, a key unit that if not informed by default is metric.
            #4 if the route is other-realtime, add to the json a key "query" with a string that is going to be used to query the question in the internet. For example, if the user asked what is the price of Bitcoin today, the query is going to be "Bitcoin price today".
            """
            completion = self.openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            # model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": system_role},
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
            case "news-summary":
                hacker_news = HackerNews()
                stories = hacker_news.get_best_stories_summary()
                all_stories = []
                for story in stories:
                    summary = self.text_summary(story['text'], words=self.summary_words)
                    all_stories.append(f"{story['title']} - {summary}")
                response = self.generate_response(user_input, f"Use this information to answer questions about any news. This is the hot news at Hacker News at the moment: {str(all_stories)}. Don't read the URLs \n. Use your knowledge to give some context to each new if possible. Answer the question as if you're on a report news podcast style. Make sure to include the take away for each news. Make sure to include your opinion.")
            case "other-realtime":
                if self.debug:
                    print(f"Searching for real time information using {self.search_sources} sources.")
                searcher = GoogleSearcher(int(self.search_sources))
                if not route.get('query'):
                    route['query'] = user_input
                results = searcher.search(route['query'])
                summaries = []
                if self.debug:
                    print("Results" + str(results) + "\n\n")
                for r in results:
                    if self.debug:
                        print(f"Extracting text from {r}")
                    extractor = WebTextExtractor(r)
                    text = extractor.get_text()
                    summary = self.text_summary(text, route['query'], words=self.summary_words)
                    summaries.append({"text": summary})
                if self.debug:
                    print ("Summaries" + str(summaries) + "\n\n")
                response = self.generate_response(user_input, f"You have access to an Internet search to look for real data information. You must answer the question. This is the contex information to answer the question: {str(summaries)}\n")
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
        exit(1)

if __name__ == "__main__":
    sandvoice = SandVoice()
    while True:
        if sandvoice.debug:
            print(sandvoice.conversation_history)
            print(sandvoice.__str__())
        sandvoice.runIt()

## TODO
# After getting the first response, have the option to press a key before start recording again
# Separate the bot messaging in a separate class
# Add some tests
# Make routes work as plugins
# Have proper error checking in multiple parts of the code
# Add temperature forecast for a week or close days
# Launch summarines in parallel
