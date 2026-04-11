import datetime
import json
import logging

import yaml
from jinja2 import Template
from types import SimpleNamespace

from common.error_handling import retry_with_backoff, handle_api_error, handle_file_error
from common.ai import _normalize_route_response, DEFAULT_ROUTE_NAME, ErrorMessage
from common.providers.base import LLMProvider

logger = logging.getLogger(__name__)


class OpenAILLMProvider(LLMProvider):
    def __init__(self, openai_client, config):
        self._client = openai_client
        self._config = config
        self.config = config  # exposed for retry_with_backoff

    def _build_system_role(self, extra_info=None):
        now = datetime.datetime.now()
        verbosity = getattr(self._config, "verbosity", "brief")
        if verbosity == "detailed":
            verbosity_instruction = (
                "Verbosity: detailed. Provide thorough, structured answers by default. "
                "Include steps/examples when helpful. If the user asks for a short answer, comply."
            )
        elif verbosity == "normal":
            verbosity_instruction = (
                "Verbosity: normal. Be concise but complete. "
                "Expand when the user explicitly asks for more detail."
            )
        else:
            verbosity_instruction = (
                "Verbosity: brief. Keep answers short by default (1-3 sentences). "
                "Avoid long lists and excessive detail unless the user explicitly asks to expand, "
                "asks for details, or says they want a longer answer."
            )

        system_role = f"""
            Your name is {self._config.botname}.
            You are an assistant written in Python by Breno Brand.
            You must answer in {self._config.language}.
            The person that is talking to you is in the {self._config.timezone} time zone.
            The person that is talking to you is located in {self._config.location}.
            Current date and time to be considered when answering the message: {now}.
            Never answer as a chat, for example reading your name in a conversation.
            DO NOT reply to messages with the format "{self._config.botname}": <message here>.
            Reply in a natural and human way.
            {verbosity_instruction}
            """
        if extra_info is not None:
            system_role = system_role + "Consider the following to answer your question: " + extra_info
        return system_role

    def _build_messages(self, user_input, conversation_history, system_role):
        """Build the messages list for chat completions.

        conversation_history entries are prefixed strings (e.g. "User: ...") matching
        the format used throughout the codebase. user_input is prefixed to stay consistent.
        """
        return (
            [{"role": "system", "content": system_role}]
            + [{"role": "user", "content": message} for message in conversation_history]
            + [{"role": "user", "content": f"User: {user_input}"}]
        )

    @retry_with_backoff(max_attempts=3, initial_delay=1)
    def _call_generate_response(self, user_input, conversation_history, extra_info=None, model=None):
        """Make the API call. Raises on failure so retry_with_backoff can retry."""
        if not model:
            model = self._config.gpt_response_model

        system_role = self._build_system_role(extra_info)
        logger.debug(
            "generate_response: length=%d verbosity=%s has_extra_info=%s model=%s history=%d",
            len(system_role),
            getattr(self._config, "verbosity", "brief"),
            extra_info is not None,
            model,
            len(conversation_history),
        )

        # Only treat explicit boolean True as enabled.
        stream_responses = (getattr(self._config, "stream_responses", False) is True)
        messages = self._build_messages(user_input, conversation_history, system_role)

        if not stream_responses:
            completion = self._client.chat.completions.create(
                model=model,
                messages=messages,
            )
            return completion.choices[0].message

        stream = self._client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
        )

        collected = []
        for event in stream:
            try:
                delta = event.choices[0].delta
                piece = getattr(delta, "content", None)
            except Exception:
                piece = None
            if piece:
                collected.append(piece)

        return SimpleNamespace(content="".join(collected))

    def generate_response(self, user_input, conversation_history, extra_info=None, model=None):
        try:
            return self._call_generate_response(
                user_input, conversation_history, extra_info=extra_info, model=model
            )
        except Exception as e:
            error_msg = handle_api_error(e, service_name="OpenAI GPT")
            logger.error("Response generation error: %s", e)
            print(error_msg)
            return ErrorMessage("Sorry, I'm having trouble right now. Please try again in a moment.")

    def stream_response_deltas(self, user_input, conversation_history, extra_info=None, model=None):
        """Yield response text deltas from the LLM stream.

        Does not mutate conversation_history — the caller is responsible for
        assembling the yielded pieces and appending the assistant turn.

        Retries are intentionally not applied — streaming retry semantics are
        ambiguous when partial output has already been emitted.
        """
        if not model:
            model = self._config.gpt_response_model

        system_role = self._build_system_role(extra_info)
        messages = self._build_messages(user_input, conversation_history, system_role)

        try:
            stream = self._client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
            )

            for event in stream:
                piece = None
                try:
                    delta = event.choices[0].delta
                    piece = getattr(delta, "content", None)
                except Exception:
                    piece = None

                if piece:
                    logger.debug("stream delta: %s", piece)
                    yield piece

        finally:
            pass  # caller assembles and appends the assistant turn

    @retry_with_backoff(max_attempts=3, initial_delay=1)
    def _call_define_route(self, user_input, model=None, extra_routes=None):
        """Make the routing API call. Raises on failure so retry_with_backoff can retry."""
        if not model:
            model = self._config.gpt_route_model
        with open(f"{self._config.sandvoice_path}/routes.yaml", 'r') as f:
            template_str = f.read()
        template = Template(template_str)
        rendered_config = template.render(location=self._config.location)
        system_role = yaml.safe_load(rendered_config)
        route_role_text = system_role['route_role']
        if extra_routes:
            route_role_text = route_role_text.rstrip() + extra_routes

        logger.info("Routing: %r", user_input)
        completion = self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": route_role_text},
                {"role": "user", "content": user_input},
            ]
        )
        route = json.loads(completion.choices[0].message.content)
        result = _normalize_route_response(route)
        logger.info("Route chosen: %s", result)
        return result

    def define_route(self, user_input, model=None, extra_routes=None):
        try:
            return self._call_define_route(user_input, model=model, extra_routes=extra_routes)
        except FileNotFoundError as e:
            error_msg = handle_file_error(e, operation="read", filename="routes.yaml")
            logger.error("Routes file error: %s", e)
            print(error_msg)
            return {"route": DEFAULT_ROUTE_NAME, "reason": "Error loading routes"}
        except json.JSONDecodeError as e:
            error_msg = "Error parsing route response from AI. Using default route."
            logger.error("Route JSON parse error: %s", e)
            print(error_msg)
            return {"route": DEFAULT_ROUTE_NAME, "reason": "Parse error"}
        except Exception as e:
            error_msg = handle_api_error(e, service_name="OpenAI GPT")
            logger.error("Route definition error: %s", e)
            print(error_msg)
            return {"route": DEFAULT_ROUTE_NAME, "reason": "API error"}

    @retry_with_backoff(max_attempts=3, initial_delay=1)
    def _call_text_summary(self, user_input, extra_info=None, words="100", model=None):
        """Make the summary API call. Raises on failure so retry_with_backoff can retry."""
        if not model:
            model = self._config.gpt_summary_model
        system_role = f"""
            You are a bot that summarizes texts in {words} words.
            If the text includes a date, mention it in the summary.
            The summary must contain the most important information from the text.
            Your answer must be in JSON format: {{"title": "some title", "text": "the summary here"}}.
            Translate the text into {self._config.language} if required.
            If a text has no content or contains an error, infer what you can from the title.
            You will receive a text and must summarize it in {words} words, returning both the title and the summary.
            The summary must help answer the user's question. For example, if the user is asking for a recipe, your answer must include the recipe.
            You may exceed the limit of {words} words only if that is necessary to summarize the text adequately.
            Do your best to stay as close as possible to the limit of {words} words.
            """
        if extra_info is not None:
            system_role = f"Consider that this is the question of the user: {extra_info}\n\n" + system_role

        completion = self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_role},
                {"role": "user", "content": user_input}
            ])
        return json.loads(completion.choices[0].message.content)

    def text_summary(self, user_input, extra_info=None, words="100", model=None):
        try:
            return self._call_text_summary(user_input, extra_info=extra_info, words=words, model=model)
        except json.JSONDecodeError as e:
            logger.error("Summary JSON parse error: %s", e)
            print("Error parsing summary response from AI.")
            return {"title": "Error", "text": "Unable to generate summary"}
        except Exception as e:
            error_msg = handle_api_error(e, service_name="OpenAI GPT")
            logger.error("Text summary error: %s", e)
            print(error_msg)
            return {"title": "Error", "text": "Unable to generate summary"}
