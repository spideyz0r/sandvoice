## Overview
This Python script allows users to interact with powerful language models such as OpenAI's GPT
through audio input and output. It's a versatile tool that converts spoken words into text,
processes them, and delivers audible responses. You can also see the conversation history
in your terminal.

## How it Works
Once the script is run, it initiates a microphone chat with the language model.
The users can ask questions through their microphone. The application then
transcribes this spoken question into text and sends it to the model. Upon
receiving the response, the application converts it back into audio, enabling
the users to hear the answer. For those who prefer reading, the text version of
the response is also printed in the terminal.

## Key Features
- Voice to text conversion
- Interaction with OpenAI's GPT model (more to be added in the future)
- Text to voice conversion
- Terminal-based conversation history

## API setup
Ensure you have your API key set in both environment variables `OPENAI_API_KEY` and `OPENWEATHERMAP_API_KEY`.

## Configuration file
It should be installed in `~/.sandvoice/config.yaml`

```
---
channels: 2
bitrate: 128
rate: 44100
chunk: 1024
tmp_files_path: /tmp/sandvoice
botname: Sandbot
timezone: EST
location: Stoney Creek, Ontario, Canada
language: English
botvoice: enabled
debug: disabled
summary_words: 100
search_sources: 3
```


Enjoy the experience!

