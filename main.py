import os
import pyaudio
import wave
import pynput
from pynput import keyboard
import lameenc
from openai import OpenAI
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame
import warnings
import sounddevice

class SandVoice:
    def __init__(self):
        self.format = pyaudio.paInt16
        self.channels = 2
        self.bitrate = 128
        self.rate = 44100
        self.chunk = 1024
        self.tmp_files_path = "/tmp/"
        self.tmp_recording = self.tmp_files_path + "recording"
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_client = OpenAI()
        self.audio = pyaudio.PyAudio()
        self.is_recording = False

    def on_press(self, key):
        if key == keyboard.Key.esc:
            self.stop_recording()
            return False

    def stop_recording(self):
        self.is_recording = False

    def start_recording(self):
        self.is_recording = True
        print("Recording started...")
        stream = self.audio.open(format=self.format, channels=self.channels,
                            rate=self.rate, input=True,
                            frames_per_buffer=self.chunk)
        frames = []

        while self.is_recording:
            data = stream.read(self.chunk)
            frames.append(data)

        stream.stop_stream()
        stream.close()
        print("Recording stopped.")

        wf = wave.open(self.tmp_recording + ".wav", 'wb')
        wf.setnchannels(self.channels)
        wf.setsampwidth(self.audio.get_sample_size(self.format))
        wf.setframerate(self.rate)
        wf.writeframes(b''.join(frames))
        wf.close()

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

    def generate_response(self, msg):
        try:
            completion = self.openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Answer in portuguese. Be very sympathetic, helpful and don't be rude or have short answers"},
                {"role": "user", "content": msg}
            ]
            )
            return completion.choices[0].message
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

if __name__ == "__main__":
    sandvoice = SandVoice()

    listener = keyboard.Listener(on_press=sandvoice.on_press)
    listener.start()

    sandvoice.start_recording()
    sandvoice.audio.terminate()
    sandvoice.convert_to_mp3()

    text = sandvoice.transcribe_and_translate()
    print(text)

    response = sandvoice.generate_response(text)
    print(response.content)

    sandvoice.text_to_speech(response.content)
    sandvoice.play_audio()

## TODO
# Remove global variables
# Use OO to encapsulate the code
# Use some fancy CLI tooling like cobra
# Read configurations such as language, voice, etc from a file
# For loop until the user breaks it
