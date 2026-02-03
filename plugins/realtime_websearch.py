import logging


def process(user_input, route, s):
    """Answer real-time questions using OpenAI web_search via Responses API."""

    try:
        query = route.get('query') or user_input

        tools = [{"type": "web_search"}]

        kwargs = {
            "model": getattr(s.config, 'gpt_response_model', None) or "gpt-5",
            "tools": tools,
            "tool_choice": "auto",
            "input": (
                "Use web search to answer the user with up-to-date information. "
                "Be concise and include sources as inline citations when available.\n\n"
                f"User query: {query}"
            ),
        }

        # Useful for debugging; includes a full list of consulted sources.
        if s.config.debug:
            kwargs["include"] = ["web_search_call.action.sources"]

        resp = s.ai.openai_client.responses.create(**kwargs)

        # Primary output text (may include inline citations).
        text = getattr(resp, 'output_text', None)
        if not text:
            # Fallback: try to extract from raw output items.
            try:
                text = resp.output[0].content[0].text
            except Exception:
                text = "I couldn't generate a response from web search."

        if s.config.debug:
            try:
                sources = []
                for item in getattr(resp, 'output', []) or []:
                    if getattr(item, 'type', None) == 'web_search_call':
                        action = getattr(item, 'action', None)
                        sources = getattr(action, 'sources', None) or []
                        break
                if sources:
                    print(f"Web search sources: {sources}")
            except Exception as e:
                logging.error(f"Failed to extract web search sources: {e}")

        return text
    except Exception as e:
        logging.error(f"Real-time web_search error: {e}")
        return "I encountered an error while searching the web. Please try again."
