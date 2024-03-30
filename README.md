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

## Plugins
Each plugin has a file under the plugins directory. All the plugins must implement a function process in this particular API:
`def process(user_input, route, s):`

## Add plugins
To add plugins you need to:
1) Update the routes.yaml; add the appropriate route for your plugin.
2) Create a file under the plugins directory with the route name, implementing the process function
3) Use the commons directory if your function could be helpful to other plugins
4) Currently all plugins have access to the "sandvoice" object and all its properties

See the echo plugin in `plugins/echo.py` for an example.

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
push_to_talk: disabled
rss_news: https://feeds.bbci.co.uk/news/rss.xml
rss_news_max_items: 5
linux_warnings: disabled
```


Enjoy the experience!

