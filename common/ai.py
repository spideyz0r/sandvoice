from openai import OpenAI
from jinja2 import Template
import datetime, json, yaml, warnings, os, logging, re, uuid
from common.error_handling import retry_with_backoff, setup_error_logging, handle_api_error, handle_file_error


# OpenAI TTS rejects inputs above ~4096 characters. Use 3800 as a conservative
# default to leave headroom for any encoding/edge-case variations in length.
DEFAULT_TTS_MAX_CHARS = 3800


SENTENCE_BREAK_RE = re.compile(r"[.!?]\s+")


def split_text_for_tts(text, max_chars = DEFAULT_TTS_MAX_CHARS):
    """Split text into chunks that fit within the TTS input size limit.

    Heuristic split priority within each window of up to max_chars:
    1) paragraph breaks ("\n\n")
    2) single newlines ("\n")
    3) sentence boundaries (SENTENCE_BREAK_RE)
    4) spaces
    5) hard cut at max_chars

    Notes/limitations:
    - sentence boundary detection is heuristic and may behave oddly for
      abbreviations ("Dr."), URLs, etc.
    - chunks are stripped; the remaining text is left-stripped after each split.
    """
    if text is None:
        return []

    remaining = str(text).strip()
    if not remaining:
        return []

    chunks = []
    # Heuristic sentence splitting; may not be perfect for abbreviations/URLs.
    # Keep this conservative to avoid splitting on ':' (timestamps) and ';' (lists).

    while len(remaining) > max_chars:
        window = remaining[: max_chars + 1]

        split_at = window.rfind("\n\n")
        if split_at != -1:
            # Do not include delimiter; remaining text is lstrip()'d below.
            split_at = min(split_at, max_chars)
        else:
            split_at = window.rfind("\n")
            if split_at != -1:
                # Do not include delimiter; remaining text is lstrip()'d below.
                split_at = min(split_at, max_chars)

        if split_at == -1:
            last_sentence_end = None
            for m in SENTENCE_BREAK_RE.finditer(window):
                last_sentence_end = m.end()
            if last_sentence_end is not None:
                split_at = min(last_sentence_end, max_chars)

        if split_at == -1 or split_at < 1:
            split_at = window.rfind(" ")
            # Unlike newline splitting, do not include the delimiter. We lstrip()
            # the remaining text below, so the space is removed without affecting
            # the chunk size.
            if split_at != -1:
                split_at = min(split_at, max_chars)

        if split_at == -1 or split_at < 1:
            split_at = max_chars

        chunk = remaining[:split_at].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_at:].lstrip()

    if remaining:
        chunks.append(remaining)

    return chunks


class ErrorMessage:
    """Simple message object for error responses"""
    def __init__(self, content):
        self.content = content


class AI:
    def __init__(self, config):
        self.config = config

        # Set up error logging
        setup_error_logging(config)

        # Check for required API key
        if not os.environ.get('OPENAI_API_KEY'):
            error_msg = "Missing OPENAI_API_KEY environment variable. Please set it and try again."
            print(f"Error: {error_msg}")
            raise ValueError(error_msg)

        self.openai_client = OpenAI(timeout=self.config.api_timeout)
        self.conversation_history = []

    @retry_with_backoff(max_attempts=3, initial_delay=1)
    def transcribe_and_translate(self, model = None):
        if not model:
            model = self.config.speech_to_text_model

        try:
            with open(self.config.tmp_recording + ".mp3", "rb") as file:
                transcript = self.openai_client.audio.translations.create(
                    model = model,
                    file = file
                )
            return transcript.text
        except FileNotFoundError as e:
            error_msg = handle_file_error(e, operation="read", filename="recording")
            if self.config.debug:
                logging.error(f"Transcription file error: {e}")
            print(error_msg)
            raise
        except Exception as e:
            error_msg = handle_api_error(e, service_name="OpenAI Whisper")
            if self.config.debug:
                logging.error(f"Transcription error: {e}")
            print(error_msg)
            raise

    @retry_with_backoff(max_attempts=3, initial_delay=1)
    def generate_response(self, user_input, extra_info = None, model = None):
        try:
            if not model:
                model = self.config.gpt_response_model

            # Add to conversation history only if not already present (prevents duplicates during retries)
            user_message = "User: " + user_input
            if not self.conversation_history or self.conversation_history[-1] != user_message:
                self.conversation_history.append(user_message)

            now = datetime.datetime.now()
            system_role = f"""
            Your name is {self.config.botname}.
            Your are an assisten written in Python by Breno Brand.
            You Answer must be in {self.config.language}.
            The person that is talking to you is in the {self.config.timezone} time zone.
            The person that is talking to you is located in {self.config.location}.
            Current date and time to be considered when answering the message: {now}.
            Never answer as a chat, for example reading your name in a conversation.
            DO NOT reply to messages with the format "{self.config.botname}": <message here>.
            Reply in a natural and human way.
            """
            if extra_info != None:
                system_role = system_role + "Consider the following to answer your question: " + extra_info
            if self.config.debug:
                print (f"System role: {system_role}")
            # Be very sympathetic, helpful and don't be rude or have short answers"

            completion = self.openai_client.chat.completions.create(
            model = model,
            messages = [
                {"role": "system", "content": system_role},
                ] + [{"role": "user", "content": message} for message in self.conversation_history]
            )
            self.conversation_history.append(f"{self.config.botname}: " + completion.choices[0].message.content)
            return completion.choices[0].message
        except Exception as e:
            error_msg = handle_api_error(e, service_name="OpenAI GPT")
            if self.config.debug:
                logging.error(f"Response generation error: {e}")
            print(error_msg)
            return ErrorMessage("Sorry, I'm having trouble right now. Please try again in a moment.")

    @retry_with_backoff(max_attempts=3, initial_delay=1)
    def define_route(self, user_input, model = None):
        try:
            if not model:
                model = self.config.gpt_route_model
            with open(f"{self.config.sandvoice_path}/routes.yaml", 'r') as f:
                template_str = f.read()
            template = Template(template_str)
            rendered_config = template.render(location=self.config.location)
            system_role = yaml.safe_load(rendered_config)

            completion = self.openai_client.chat.completions.create(
            model = model,
            messages = [
                {"role": "system", "content": system_role['route_role']},
                {"role": "user", "content": user_input}
            ])
            return json.loads(completion.choices[0].message.content)
        except FileNotFoundError as e:
            error_msg = handle_file_error(e, operation="read", filename="routes.yaml")
            if self.config.debug:
                logging.error(f"Routes file error: {e}")
            print(error_msg)
            # Return default route as fallback
            return {"route": "default-route", "reason": "Error loading routes"}
        except json.JSONDecodeError as e:
            error_msg = "Error parsing route response from AI. Using default route."
            if self.config.debug:
                logging.error(f"Route JSON parse error: {e}")
            print(error_msg)
            return {"route": "default-route", "reason": "Parse error"}
        except Exception as e:
            error_msg = handle_api_error(e, service_name="OpenAI GPT")
            if self.config.debug:
                logging.error(f"Route definition error: {e}")
            print(error_msg)
            return {"route": "default-route", "reason": "API error"}

    @retry_with_backoff(max_attempts=3, initial_delay=1)
    def text_summary(self, user_input, extra_info = None, words = "100", model = None):
        try:
            if not model:
                model = self.config.gpt_summary_model
            if self.config.debug:
                print("Summary words: " + words)
                print("Before: " + user_input)
            system_role = f"""
            You're a bot summaries texts in {words} words.
            If there is a date of the text you are reading, mention the date in the summary.
            The summary must content the most important information of the text.
            Your answer will be in json format: {{"title": "some title", "text": "the summary here"}}.
            The text must be translated to {self.config.language} if required.
            If one of the texts has no content or has an error, figure something out from the title.
            You will receive a text and you need to summarize it in {words} words and return the title and the summary.
            You must be able to answer the user's question with the summary. For example, if the user is asking for a recipe, your answer must have the recipe.
            The only condition that will allow you bypass the limite of {words} words is if that amount of words is not enough to summarize the text.
            Do your best to be as close to the limit  of {words} words as possible.
            """

            if self.config.debug:
                print(system_role)
            if extra_info != None:
                system_role = "Consider that this is the question of the user: {extra_info}" + system_role

            completion = self.openai_client.chat.completions.create(
            model = model,
            messages = [
                {"role": "system", "content": system_role},
                {"role": "user", "content": user_input}
            ])
            if self.config.debug:
                print("After: " +completion.choices[0].message.content + "\n")
            return json.loads(completion.choices[0].message.content)
        except json.JSONDecodeError as e:
            error_msg = "Error parsing summary response from AI."
            if self.config.debug:
                logging.error(f"Summary JSON parse error: {e}")
            print(error_msg)
            return {"title": "Error", "text": "Unable to generate summary"}
        except Exception as e:
            error_msg = handle_api_error(e, service_name="OpenAI GPT")
            if self.config.debug:
                logging.error(f"Text summary error: {e}")
            print(error_msg)
            return {"title": "Error", "text": "Unable to generate summary"}

    @retry_with_backoff(max_attempts=3, initial_delay=1)
    def text_to_speech(self, text, model = None, voice = None):
        if not model:
            model = self.config.text_to_speech_model
        if not voice:
            voice = self.config.bot_voice_model

        try:
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            chunks = split_text_for_tts(text)
            if not chunks:
                return []

            response_id = uuid.uuid4().hex
            output_files = []

            try:
                for i, chunk in enumerate(chunks, start=1):
                    speech_file_path = os.path.join(
                        self.config.tmp_files_path,
                        f"tts-response-{response_id}-chunk-{i:03d}.mp3",
                    )
                    response = self.openai_client.audio.speech.create(
                        model = model,
                        voice = voice,
                        input = chunk
                    )
                    output_files.append(speech_file_path)
                    response.stream_to_file(speech_file_path)
            except Exception:
                for f in output_files:
                    try:
                        if os.path.exists(f):
                            os.remove(f)
                    except Exception:
                        # Best-effort cleanup: ignore errors when deleting temporary files
                        pass
                raise

            return output_files
        except Exception as e:
            # Avoid noisy tracebacks by default; keep details in debug or when file logging is enabled.
            if self.config.debug:
                logging.exception("Text-to-speech error")
            else:
                logging.error(f"Text-to-speech error: {e}")

            if self.config.fallback_to_text_on_audio_error:
                print(handle_api_error(e, service_name="OpenAI TTS"))
                return []

            print(handle_api_error(e, service_name="OpenAI TTS"))
            raise
