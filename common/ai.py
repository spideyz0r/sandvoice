from openai import OpenAI
from jinja2 import Template
import datetime, json, yaml, warnings, os, logging
from common.error_handling import retry_with_backoff, setup_error_logging, handle_api_error, handle_file_error


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

        self.openai_client = OpenAI()
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
            self.conversation_history.append("User: " + user_input)
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
            # Return a message object-like string for compatibility
            class ErrorMessage:
                def __init__(self, content):
                    self.content = content
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
            speech_file_path = self.config.tmp_recording + ".mp3"
            response = self.openai_client.audio.speech.create(
                model = model,
                voice = "nova",
                input = text
            )
            response.stream_to_file(speech_file_path)
        except Exception as e:
            error_msg = handle_api_error(e, service_name="OpenAI TTS")
            if self.config.debug:
                logging.error(f"Text-to-speech error: {e}")
            print(error_msg)
            # Don't raise - allow fallback to text-only mode
            if self.config.fallback_to_text_on_audio_error:
                print("Falling back to text-only mode.")
            else:
                raise
