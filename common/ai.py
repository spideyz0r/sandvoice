from openai import OpenAI
import os, logging, re
from common.error_handling import setup_error_logging

logger = logging.getLogger(__name__)

# OpenAI TTS rejects inputs above ~4096 characters. Use 3800 as a conservative
# default to leave headroom for any encoding/edge-case variations in length.
DEFAULT_TTS_MAX_CHARS = 3800
DEFAULT_ROUTE_NAME = "default-route"
_ROUTE_NAME_ALIASES = {
    "default-rote": DEFAULT_ROUTE_NAME,
}


SENTENCE_BREAK_RE = re.compile(r"[.!?]\s+")


# Streaming chunking defaults are intentionally smaller than DEFAULT_TTS_MAX_CHARS
# to reduce time-to-first-audio and keep queued chunks short.
DEFAULT_STREAM_MAX_CHARS = 1200


def normalize_route_name(route_name):
    """Map known legacy route names to the canonical identifier."""
    if not isinstance(route_name, str):
        return route_name
    normalized = route_name.strip()
    return _ROUTE_NAME_ALIASES.get(normalized, normalized)


def _normalize_route_response(route):
    """Validate route response shape and normalize the route identifier."""
    if not isinstance(route, dict):
        logger.warning("Invalid route response type: %s", type(route).__name__)
        return {"route": DEFAULT_ROUTE_NAME, "reason": "Invalid route response"}

    normalized_route = normalize_route_name(route.get("route"))
    reason = route.get("reason")
    if not isinstance(normalized_route, str) or not normalized_route:
        logger.warning("Invalid route name in response: %r", route)
        return {"route": DEFAULT_ROUTE_NAME, "reason": "Invalid route response"}
    if not isinstance(reason, str) or not reason:
        logger.warning("Invalid route reason in response: %r", route)
        return {"route": DEFAULT_ROUTE_NAME, "reason": "Invalid route response"}

    normalized = dict(route)
    normalized["route"] = normalized_route
    return normalized


def pop_streaming_chunk(buffer, boundary="sentence", min_chars=200, max_chars=DEFAULT_STREAM_MAX_CHARS):
    """Pop a speakable chunk from a growing streaming buffer.

    Returns:
        (chunk, remainder)
        - chunk: str|None (None means not enough buffered yet)
        - remainder: str
    """
    if buffer is None:
        return None, ""

    remaining = str(buffer)
    if not remaining.strip():
        return None, remaining

    # Prefer natural boundaries.
    if boundary == "paragraph":
        idx = remaining.find("\n\n")
        if idx != -1:
            end = idx + 2
            raw_chunk = remaining[:end]
            raw_remainder = remaining[end:]
            candidate = raw_chunk.strip()
            if len(candidate) >= min_chars:
                remainder = raw_remainder.lstrip()
                if raw_chunk.rstrip() != raw_chunk and candidate and remainder:
                    candidate = candidate + " "
                return candidate, remainder
    else:
        for match in SENTENCE_BREAK_RE.finditer(remaining):
            end = match.end()
            raw_chunk = remaining[:end]
            raw_remainder = remaining[end:]
            candidate = raw_chunk.strip()
            if len(candidate) >= min_chars:
                remainder = raw_remainder.lstrip()
                if raw_chunk.rstrip() != raw_chunk and candidate and remainder:
                    candidate = candidate + " "
                return candidate, remainder

    # If buffer is getting too large, fall back to a soft cut.
    if len(remaining) > max_chars:
        cut = remaining.rfind(" ", 0, max_chars)
        if cut == -1 or cut < int(max_chars * 0.6):
            cut = max_chars
        raw_chunk = remaining[:cut]
        raw_remainder = remaining[cut:]
        candidate = raw_chunk.strip()
        if candidate:
            remainder = raw_remainder.lstrip()
            if raw_remainder[:1].isspace() and candidate and remainder:
                candidate = candidate + " "
            return candidate, remainder

    return None, remaining


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


_SUPPORTED_PROVIDERS = {"openai"}


def _validate_provider_names(config):
    """Raise ValueError for any unsupported provider name.

    Called by from_config before the API-key check so a misconfigured
    provider gives an actionable error rather than a misleading missing-key
    message.  _build_*_provider functions also validate as a safety net for
    direct callers; both reference _SUPPORTED_PROVIDERS as the single source
    of truth.
    """
    for field in ("llm_provider", "tts_provider", "stt_provider"):
        name = getattr(config, field, "openai")
        if name not in _SUPPORTED_PROVIDERS:
            error_msg = f"Unknown {field}: {name!r}"
            print(f"Error: {error_msg}")
            raise ValueError(error_msg)


def _build_llm_provider(config, openai_client):
    # Deferred import to avoid circular dependency: openai_llm imports from common.ai
    from common.providers import OpenAILLMProvider
    provider = getattr(config, "llm_provider", "openai")
    if provider == "openai":
        return OpenAILLMProvider(openai_client, config)
    raise ValueError(f"Unknown llm_provider: {provider!r}")


def _build_tts_provider(config, openai_client):
    from common.providers import OpenAITTSProvider
    provider = getattr(config, "tts_provider", "openai")
    if provider == "openai":
        return OpenAITTSProvider(openai_client, config)
    raise ValueError(f"Unknown tts_provider: {provider!r}")


def _build_stt_provider(config, openai_client):
    from common.providers import OpenAISTTProvider
    provider = getattr(config, "stt_provider", "openai")
    if provider == "openai":
        return OpenAISTTProvider(openai_client, config)
    raise ValueError(f"Unknown stt_provider: {provider!r}")


class AI:
    def __init__(self, llm, tts, stt, config, *, openai_client=None):
        self.config = config
        self._llm = llm
        self._tts = tts
        self._stt = stt
        self._openai_client = openai_client
        self.conversation_history = []

    @property
    def openai_client(self):
        """Return the underlying OpenAI client for plugins that use the API directly.

        Raises AttributeError if the AI was not constructed via from_config or the
        configured provider does not expose an OpenAI client.
        """
        if self._openai_client is None:
            raise AttributeError(
                "openai_client is not available: AI was not constructed via "
                "from_config, or the configured provider does not use an OpenAI client."
            )
        return self._openai_client

    @classmethod
    def from_config(cls, config):
        setup_error_logging(config)
        # Validate provider names before checking the API key so a misconfigured
        # provider gives an actionable error rather than "Missing OPENAI_API_KEY".
        _validate_provider_names(config)
        if not os.environ.get('OPENAI_API_KEY'):
            error_msg = "Missing OPENAI_API_KEY environment variable. Please set it and try again."
            print(f"Error: {error_msg}")
            raise ValueError(error_msg)
        openai_client = OpenAI(timeout=config.api_timeout)
        llm = _build_llm_provider(config, openai_client)
        tts = _build_tts_provider(config, openai_client)
        stt = _build_stt_provider(config, openai_client)
        return cls(llm, tts, stt, config, openai_client=openai_client)

    def generate_response(self, user_input, extra_info=None, model=None):
        # Append user turn first so history is consistent even if the call fails.
        # Pass history[:-1] to the provider — provider appends user_input via
        # _build_messages, avoiding a duplicate if history already ends with this turn.
        user_message = "User: " + user_input
        if not self.conversation_history or self.conversation_history[-1] != user_message:
            self.conversation_history.append(user_message)
        result = self._llm.generate_response(
            user_input, self.conversation_history[:-1], extra_info=extra_info, model=model
        )
        self.conversation_history.append(f"{self.config.botname}: " + result.content)
        return result

    def stream_response_deltas(self, user_input, extra_info=None, model=None):
        """Yield response text deltas from the LLM stream.

        Appends the user turn to conversation_history immediately, then yields
        deltas from the provider. The assistant turn is only appended on successful
        stream completion — partial output is discarded on failure.

        The provider receives history without the current user turn; it appends
        user_input via _build_messages.

        Retries are intentionally not applied — streaming retry semantics are
        ambiguous when partial output has already been emitted.
        """
        user_message = "User: " + user_input
        if not self.conversation_history or self.conversation_history[-1] != user_message:
            self.conversation_history.append(user_message)

        # provider_history excludes the just-appended user turn — provider adds it
        provider_history = self.conversation_history[:-1]

        collected = []
        stream_completed = False

        try:
            for piece in self._llm.stream_response_deltas(
                user_input, provider_history, extra_info=extra_info, model=model
            ):
                collected.append(piece)
                if self.config.debug:
                    print(piece, end="", flush=True)
                yield piece
            stream_completed = True
        finally:
            if self.config.debug:
                print("", flush=True)
            if stream_completed:
                self.conversation_history.append(
                    f"{self.config.botname}: " + "".join(collected)
                )

    def transcribe_and_translate(self, model=None, audio_file_path=None):
        return self._stt.transcribe(audio_file_path=audio_file_path, model=model)

    def define_route(self, user_input, model=None, extra_routes=None):
        return self._llm.define_route(user_input, model=model, extra_routes=extra_routes)

    def text_to_speech(self, text, model=None, voice=None):
        return self._tts.text_to_speech(text, model=model, voice=voice)

    def text_summary(self, user_input, extra_info=None, words="100", model=None):
        return self._llm.text_summary(user_input, extra_info=extra_info, words=words, model=model)
