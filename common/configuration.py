import os, yaml

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
            "unit": "metric",
            "language": "English",
            "debug": "disabled",
            "summary_words": "100",
            "search_sources": "4",
            "push_to_talk": "disabled",
            "rss_news": "https://feeds.bbci.co.uk/news/rss.xml",
            "rss_news_max_items": "5",
            "linux_warnings": "enabled",
            "gpt_summary_model" : "gpt-3.5-turbo",
            "gpt_route_model" : "gpt-3.5-turbo",
            "gpt_response_model" : "gpt-3.5-turbo",
            "speech_to_text_model" : "whisper-1",
            "text_to_speech_model" : "tts-1",
            "bot_voice_model" : "nova",
            "bot_voice": "enabled"
        }
        self.config = self.load_defaults()
        self.load_config()

    def load_defaults(self):
        if not os.path.exists(self.config_file):
            return self.defaults
        with open(self.config_file, "r") as f:
            data = yaml.safe_load(f)
        # combine both dicts, data overrides defaults
        return {**self.defaults, **data}

    def load_config(self):
        self.channels = self.get("channels")
        self.bitrate = self.get("bitrate")
        self.rate = self.get("rate")
        self.chunk = self.get("chunk")
        self.tmp_files_path = self.get("tmp_files_path")
        self.botname = self.get("botname")
        self.timezone = self.get("timezone")
        self.location = self.get("location")
        self.unit = self.get("unit")
        self.language = self.get("language")
        self.summary_words = self.get("summary_words")
        self.search_sources = self.get("search_sources")
        self.rss_news = self.get("rss_news")
        self.rss_news_max_items = self.get("rss_news_max_items")
        self.tmp_recording = self.tmp_files_path + "recording"
        self.debug = self.get("debug").lower() == "enabled"
        self.bot_voice = self.get("bot_voice").lower() == "enabled"
        self.push_to_talk = self.get("push_to_talk").lower() == "enabled"
        self.linux_warnings = self.get("linux_warnings").lower() == "enabled"
        self.sandvoice_path = f"{os.path.dirname(os.path.realpath(__file__))}/../"
        self.plugin_path = f"{self.sandvoice_path}plugins/"
        self.gpt_summary_model = self.get("gpt_summary_model")
        self.gpt_route_model = self.get("gpt_route_model")
        self.gpt_response_model = self.get("gpt_response_model")
        self.speech_to_text_model = self.get("speech_to_text_model")
        self.text_to_speech_model = self.get("text_to_speech_model")
        self.bot_voice_model = self.get("bot_voice_model")

    def get(self, key):
            return self.config.get(key, self.defaults[key])
