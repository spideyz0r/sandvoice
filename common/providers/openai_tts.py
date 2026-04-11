import logging
import os
import threading
import uuid
import warnings

from common.ai import split_text_for_tts
from common.error_handling import retry_with_backoff, handle_api_error
from common.providers.base import TTSProvider

logger = logging.getLogger(__name__)


class OpenAITTSProvider(TTSProvider):
    def __init__(self, openai_client, config):
        self._client = openai_client
        self._config = config
        self.config = config  # exposed for retry_with_backoff

    def text_to_speech(self, text, model=None, voice=None) -> list:
        logger.debug("TTS generation called from thread %s: text=%s...",
                     threading.current_thread().name, text[:50] if text else "empty")
        logger.debug("TTS generation full text length: %d chars", len(text) if text else 0)
        model = model or self._config.text_to_speech_model
        voice = voice or self._config.bot_voice_model
        try:
            return self._generate_tts_files(text, model, voice)
        except Exception as e:
            logger.error("Text-to-speech failed: %s", handle_api_error(e, service_name="OpenAI TTS"))
            logger.debug("Text-to-speech exception details:", exc_info=True)
            return []

    @retry_with_backoff(max_attempts=3, initial_delay=1)
    def _generate_tts_files(self, text, model, voice):
        """Generate TTS audio files. Raises on failure so @retry_with_backoff can retry."""
        chunks = split_text_for_tts(text)
        if not chunks:
            return []

        response_id = uuid.uuid4().hex
        output_files = []

        try:
            for i, chunk in enumerate(chunks, start=1):
                speech_file_path = os.path.join(
                    self._config.tmp_files_path,
                    f"tts-response-{response_id}-chunk-{i:03d}.mp3",
                )
                response = self._client.audio.speech.create(
                    model=model,
                    voice=voice,
                    input=chunk
                )
                output_files.append(speech_file_path)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", DeprecationWarning)
                    response.stream_to_file(speech_file_path)
                logger.debug("TTS file created: thread=%s, file=%s",
                             threading.current_thread().name, os.path.basename(speech_file_path))
        except Exception:
            for f in output_files:
                try:
                    if os.path.exists(f):
                        os.remove(f)
                except Exception:
                    pass  # best-effort cleanup
            raise

        return output_files
