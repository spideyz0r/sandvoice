import logging


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

        # Craft voice-friendly prompt
        voice_prompt = (
            f"{query}\n\n"
            "Provide a brief, direct answer suitable for a voice assistant. "
            "Keep it concise (2-3 sentences max). "
            "Do NOT include URLs, citations, or links in your response."
        )

        resp = s.ai.openai_client.responses.create(
            model = getattr(s.config, 'gpt_response_model', None) or "gpt-5-mini",
            tools = [{"type": "web_search"}],
            tool_choice = "auto",
            input = voice_prompt,
            include = include_params,
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

        return resp.output_text or "I couldn't find anything useful on the web for that query."
    except Exception as e:
        logging.error(f"Real-time web_search error: {e}")
        return "I encountered an error while searching the web. Please try again."
