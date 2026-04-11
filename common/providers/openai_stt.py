import logging
import os

from common.error_handling import retry_with_backoff, handle_api_error, handle_file_error
from common.providers.base import STTProvider

logger = logging.getLogger(__name__)


class OpenAISTTProvider(STTProvider):
    def __init__(self, openai_client, config):
        self._client = openai_client
        self._config = config
        self.config = config  # exposed for retry_with_backoff

    @retry_with_backoff(max_attempts=3, initial_delay=1)
    def transcribe(self, audio_file_path=None, model=None) -> str:
        """Transcribe audio file to text.

        If `audio_file_path` is None, use the configured temporary recording path.
        Return the transcript string.
        """
        if not model:
            model = self._config.speech_to_text_model

        file_path = audio_file_path if audio_file_path else (self._config.tmp_recording + ".mp3")

        task = getattr(self._config, 'speech_to_text_task', 'translate')
        language_hint = getattr(self._config, 'speech_to_text_language', '')
        translate_provider = getattr(self._config, 'speech_to_text_translate_provider', 'whisper')
        translate_model = getattr(self._config, 'speech_to_text_translate_model', 'gpt-5-mini')

        try:
            with open(file_path, "rb") as file:
                if task == 'transcribe':
                    kwargs = {"model": model, "file": file}
                    if language_hint:
                        kwargs["language"] = language_hint
                    transcript = self._client.audio.transcriptions.create(**kwargs)
                    return transcript.text

                if translate_provider == 'whisper':
                    transcript = self._client.audio.translations.create(
                        model=model,
                        file=file
                    )
                    return transcript.text

                kwargs = {"model": model, "file": file}
                if language_hint:
                    kwargs["language"] = language_hint
                transcript = self._client.audio.transcriptions.create(**kwargs)
        except FileNotFoundError as e:
            error_msg = handle_file_error(e, operation="read", filename=os.path.basename(file_path))
            logger.error("Transcription file error: %s", e)
            print(error_msg)
            raise
        except Exception as e:
            error_msg = handle_api_error(e, service_name="OpenAI Whisper")
            logger.error("Transcription error: %s", e)
            print(error_msg)
            raise

        # Chat-completions translation — separate try block to avoid mislabelling errors
        source_text = transcript.text or ""
        if not source_text.strip():
            return ""

        try:
            completion = self._client.chat.completions.create(
                model=translate_model,
                messages=[
                    {
                        "role": "system",
                        "content": "Translate the user's text to English. Return only the translated text.",
                    },
                    {"role": "user", "content": source_text},
                ],
            )
            return (completion.choices[0].message.content or "").strip()
        except Exception as e:
            error_msg = handle_api_error(e, service_name="OpenAI Chat Completions")
            logger.error("Translation error (chat completions): %s", e)
            print(error_msg)
            raise
