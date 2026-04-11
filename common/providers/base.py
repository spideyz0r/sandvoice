from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    def generate_response(self, user_input, conversation_history, extra_info=None, model=None):
        """Return a response object with a `.content` attribute (str)."""

    @abstractmethod
    def stream_response_deltas(self, user_input, conversation_history, extra_info=None, model=None):
        """Yield str deltas from the LLM stream."""

    @abstractmethod
    def define_route(self, user_input, model=None, extra_routes=None):
        """Return a route dict: {"route": str, "reason": str}."""

    @abstractmethod
    def text_summary(self, user_input, extra_info=None, words="100", model=None):
        """Return a summary dict: {"title": str, "text": str}."""


class TTSProvider(ABC):
    @abstractmethod
    def text_to_speech(self, text, model=None, voice=None) -> list:
        """Convert text to audio. Return a list of audio file paths (str)."""


class STTProvider(ABC):
    @abstractmethod
    def transcribe(self, audio_file_path=None, model=None) -> str:
        """Transcribe audio file to text.

        If `audio_file_path` is None, use the configured temporary recording path.
        Return the transcript string.
        """
