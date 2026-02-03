import logging


def process(user_input, route, s):
    """Answer real-time questions using OpenAI `web_search` (Responses API)."""

    try:
        query = route.get('query') or user_input
        resp = s.ai.openai_client.responses.create(
            model = getattr(s.config, 'gpt_response_model', None) or "gpt-5",
            tools = [{"type": "web_search"}],
            tool_choice = "auto",
            input = query,
        )
        return resp.output_text or "I couldn't find anything useful on the web for that query."
    except Exception as e:
        logging.error(f"Real-time web_search error: {e}")
        return "I encountered an error while searching the web. Please try again."
