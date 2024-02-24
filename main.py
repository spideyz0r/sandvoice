import os
import pyaudio
import wave
import pynput
from pynput import keyboard
import lameenc
from openai import OpenAI
import pygame
import warnings

FORMAT = pyaudio.paInt16
CHANNELS = 2
RATE = 44100
CHUNK = 1024
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
tmp_recording = "recording"

client = OpenAI()
audio = pyaudio.PyAudio()
is_recording = False

def start_recording():
    global is_recording
    is_recording = True
    print("Recording started...")
    stream = audio.open(format=FORMAT, channels=CHANNELS,
                        rate=RATE, input=True,
                        frames_per_buffer=CHUNK)
    frames = []

    while is_recording:
        data = stream.read(CHUNK)
        frames.append(data)

    stream.stop_stream()
    stream.close()
    print("Recording stopped.")

    wf = wave.open(tmp_recording + ".wav", 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(audio.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()

def stop_recording():
    global is_recording
    is_recording = False

def on_press(key):
    if key == keyboard.Key.esc:
        stop_recording()
        return False

def transcribe_and_translate():
    with open(tmp_recording + ".mp3", "rb") as file:
        transcript = client.audio.translations.create(
            model="whisper-1",
            file=file
        )
    return transcript.text

def convert2mp3():
    lame = lameenc.Encoder()
    lame.set_bit_rate(128)
    lame.set_in_sample_rate(RATE)
    lame.set_channels(CHANNELS)
    lame.set_quality(2)
    with open(tmp_recording + ".wav", "rb") as wav_file, open(tmp_recording + ".mp3", "wb") as mp3_file:
        mp3_data = lame.encode(wav_file.read())
        mp3_file.write(mp3_data)

def generate_response(msg):
    try:
        completion = client.chat.completions.create(
          model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Answer in portuguese"},
            {"role": "user", "content": msg}
        ]
        )
        return completion.choices[0].message
    except Exception as e:
        print("A general error occurred:", e)
        return "Sorry, I'm having trouble thinking right now. Could you try again later?"

def text2Speech(text):
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    speech_file_path = tmp_recording + ".mp3"
    response = client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=text
    )
    response.stream_to_file(speech_file_path)

def playAudio():
    pygame.mixer.init()
    pygame.mixer.music.load(tmp_recording + ".mp3")
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)

if __name__ == "__main__":
    listener = keyboard.Listener(on_press=on_press)
    listener.start()

    start_recording()
    audio.terminate()
    convert2mp3()

    text = transcribe_and_translate()
    print(text)

    response = generate_response(text)
    print(response.content)

    text2Speech(response.content)
    playAudio()

## TODO
# Remove global variables
# Use OO to encapsulate the code
# Read configurations such as language, voice, etc from a file