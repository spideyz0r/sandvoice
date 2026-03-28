import logging
import re


def _strip_urls(text):
    """Remove URLs and inline citations from text, preserving plain-text references."""
    # Remove ([label](url)) — outer parens wrapping a markdown link
    text = re.sub(r'\s*\(\s*\[[^\]]*\]\(https?://[^)]*\)\s*\)', '', text)
    # Remove remaining markdown links [text](url) → text
    text = re.sub(r'\[([^\]]+)\]\(https?://[^)]+\)', r'\1', text)
    # Remove parenthesised bare URLs like (https://...)
    text = re.sub(r'\s*\(https?://[^)]*\)', '', text)
    # Remove stray bare URLs
    text = re.sub(r'https?://\S+', '', text)
    return text.strip()


def process(user_input, route, s):
    """
    Answer real-time questions using OpenAI `web_search` (Responses API).

    Configuration:
      - gpt_response_model: Model to use for web search (default: gpt-5-mini)
        Options: gpt-5-mini (cheapest), gpt-5, gpt-4.1, gpt-4.1-mini, o4-mini
      - debug: When enabled, prints web search sources consulted

    Cost per query with gpt-5-mini: ~$0.013 (tool call + tokens)
    """

    try:
        query = route.get('query') or user_input

        # Include sources in response if debug mode enabled
        include_params = ["web_search_call.action.sources"] if s.config.debug else []

        system_instructions = (
            "You are a voice assistant. Answer briefly (2-3 sentences). "
            "NEVER include URLs, links, or markdown in your response. "
            f"Always respond in the same language as the user's question: {user_input}"
        )

        resp = s.ai.openai_client.responses.create(
            model=getattr(s.config, 'gpt_response_model', None) or "gpt-5-mini",
            instructions=system_instructions,
            tools=[{"type": "web_search"}],
            tool_choice="auto",
            input=query,
            include=include_params,
        )

        # Print sources in debug mode
        if s.config.debug and hasattr(resp, 'output'):
            for item in resp.output:
                if hasattr(item, 'type') and item.type == 'web_search_call':
                    if hasattr(item, 'action') and hasattr(item.action, 'sources'):
                        sources = item.action.sources or []
                        if sources:
                            print(f"\nWeb search consulted {len(sources)} sources:")
                            for src in sources[:5]:  # Show first 5
                                print(f"  - {src}")
                            if len(sources) > 5:
                                print(f"  ... and {len(sources) - 5} more")

        text = resp.output_text or "I couldn't find anything useful on the web for that query."
        return _strip_urls(text)
    except Exception as e:
        logging.error(f"Real-time web_search error: {e}")
        return "I encountered an error while searching the web. Please try again."
