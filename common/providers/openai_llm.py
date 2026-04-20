import json
import logging
from collections import namedtuple

import yaml
from jinja2 import Template
from types import SimpleNamespace

from common.error_handling import retry_with_backoff, handle_api_error, handle_file_error
from common.ai import _normalize_route_response, DEFAULT_ROUTE_NAME, ErrorMessage
from common.prompt import build_system_role
from common.providers.base import LLMProvider

_WebSearchErrorResult = namedtuple("_WebSearchErrorResult", ["output_text"])

logger = logging.getLogger(__name__)


class OpenAILLMProvider(LLMProvider):
    def __init__(self, openai_client, config):
        self._client = openai_client
        self.config = config

    def _build_system_role(self, extra_info=None):
        return build_system_role(self.config, extra_info=extra_info)

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
            model = self.config.llm_response_model

        system_role = self._build_system_role(extra_info)
        logger.debug(
            "generate_response: length=%d verbosity=%s has_extra_info=%s model=%s history=%d",
            len(system_role),
            getattr(self.config, "verbosity", "brief"),
            extra_info is not None,
            model,
            len(conversation_history),
        )

        # Only treat explicit boolean True as enabled.
        stream_responses = (getattr(self.config, "stream_responses", False) is True)
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
            model = self.config.llm_response_model

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
    def _call_define_route(self, user_input, model=None, extra_routes=None, history=None):
        """Make the routing API call. Raises on failure so retry_with_backoff can retry."""
        if not model:
            model = self.config.llm_route_model
        with open(f"{self.config.sandvoice_path}/routes.yaml", 'r') as f:
            template_str = f.read()
        template = Template(template_str)
        rendered_config = template.render(location=self.config.location)
        system_role = yaml.safe_load(rendered_config)
        route_role_text = system_role['route_role']
        if extra_routes:
            route_role_text = route_role_text.rstrip() + extra_routes

        messages = [{"role": "system", "content": route_role_text}]
        if history:
            for entry in history:
                messages.append({"role": "user", "content": entry})
            messages.append({"role": "user", "content": f"User: {user_input}"})
        else:
            messages.append({"role": "user", "content": user_input})

        logger.info("Routing: %r (history=%d entries)", user_input, len(history) if history else 0)
        completion = self._client.chat.completions.create(
            model=model,
            messages=messages,
        )
        route = json.loads(completion.choices[0].message.content)
        result = _normalize_route_response(route)
        logger.info("Route chosen: %s", result)
        return result

    def define_route(self, user_input, model=None, extra_routes=None, history=None):
        try:
            return self._call_define_route(user_input, model=model, extra_routes=extra_routes, history=history)
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
            model = self.config.llm_summary_model
        system_role = f"""
            You are a bot that summarizes texts in {words} words.
            If the text includes a date, mention it in the summary.
            The summary must contain the most important information from the text.
            Your answer must be in JSON format: {{"title": "some title", "text": "the summary here"}}.
            Translate the text into {self.config.language} if required.
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

    @retry_with_backoff(max_attempts=3, initial_delay=1)
    def _call_one_shot(self, prompt, model=None):
        """Make the API call. Raises on failure so retry_with_backoff can retry."""
        if not model:
            model = self.config.llm_response_model
        completion = self._client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return completion.choices[0].message

    def one_shot(self, prompt, model=None):
        try:
            return self._call_one_shot(prompt, model=model)
        except Exception as e:
            error_msg = handle_api_error(e, service_name="OpenAI GPT")
            logger.error("one_shot error: %s", error_msg)
            return ErrorMessage("Sorry, I'm having trouble right now. Please try again in a moment.")

    @retry_with_backoff(max_attempts=3, initial_delay=1)
    def _call_web_search(self, query, instructions, model=None, include=None):
        """Make the Responses API call. Raises on failure so retry_with_backoff can retry."""
        if not model:
            model = self.config.llm_response_model
        return self._client.responses.create(
            model=model,
            instructions=instructions,
            tools=[{"type": "web_search"}],
            tool_choice="auto",
            input=query,
            include=include or [],
        )

    def web_search(self, query, instructions, model=None, include=None):
        try:
            return self._call_web_search(query, instructions, model=model, include=include)
        except Exception as e:
            error_msg = handle_api_error(e, service_name="OpenAI web search")
            logger.exception("Web search error: %s", error_msg)
            print(error_msg)
            return _WebSearchErrorResult(
                output_text="I encountered an error while searching the web. Please try again."
            )
