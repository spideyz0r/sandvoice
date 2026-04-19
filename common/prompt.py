import datetime
import logging

logger = logging.getLogger(__name__)


def build_system_role(config, extra_info=None):
    """Build the SandVoice system role prompt from configuration.

    This is the application-level persona shared by all LLM providers.
    Provider implementations call this function rather than building the
    prompt themselves.

    Args:
        config: Config instance supplying botname, language, timezone,
                location, and verbosity.
        extra_info: Optional string appended to the prompt as additional
                    context for the current request.

    Returns:
        str: The system role prompt string.
    """
    now = datetime.datetime.now()
    verbosity = getattr(config, "verbosity", "brief")
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

    logger.debug(
        "Building system role: botname=%r language=%r verbosity=%r extra_info=%s",
        config.botname, config.language, verbosity,
        "present" if extra_info is not None else "absent",
    )

    system_role = f"""
            Your name is {config.botname}.
            You are an assistant written in Python by Breno Brand.
            You must answer in {config.language}.
            The person that is talking to you is in the {config.timezone} time zone.
            The person that is talking to you is located in {config.location}.
            Current date and time to be considered when answering the message: {now}.
            Never answer as a chat, for example reading your name in a conversation.
            DO NOT reply to messages with the format "{config.botname}": <message here>.
            Never use symbols, always spell it out. For example say degrees instead of using the symbol. Don't say km/h, but kilometers per hour, and so on.
            Reply in a natural and human way.
            {verbosity_instruction}
            """
    extra = getattr(config, "system_prompt_extra", None)
    if isinstance(extra, str) and extra.strip():
        system_role = system_role + extra.strip() + "\n            "
        logger.debug("system_prompt_extra active (%d chars)", len(extra.strip()))
    if extra_info is not None:
        system_role = system_role + "Consider the following to answer your question: " + extra_info
    return system_role
