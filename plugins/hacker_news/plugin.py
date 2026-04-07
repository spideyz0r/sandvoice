import requests, logging, datetime

logger = logging.getLogger(__name__)

_CACHE_KEY = "hacker-news:best"
_DEFAULT_TTL_S = 28800      # 8 hours
_DEFAULT_MAX_STALE_S = 43200  # 12 hours


def _cache_key():
    return _CACHE_KEY


class HackerNews:
    def __init__(self, timeout=10):
        self.base_url = "https://hacker-news.firebaseio.com/v0/"
        self.limit = 5
        self.timeout = timeout

    def get_best_story_ids(self):
        try:
            response = requests.get(self.base_url + "beststories.json", timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error("Hacker News API error: %s", e)
            return []

    def get_story_details(self, story_id):
        try:
            response = requests.get(self.base_url + f"item/{story_id}.json", timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error("Hacker News story error: %s", e)
            return None

    def get_best_story_briefs(self):
        story_ids = self.get_best_story_ids()[:self.limit]
        briefs = []

        for story_id in story_ids:
            try:
                story = self.get_story_details(story_id)
                if not story:
                    continue

                story_time = story.get('time')
                if story_time:
                    try:
                        story_time = datetime.datetime.fromtimestamp(story_time).isoformat()
                    except Exception:
                        story_time = None

                briefs.append({
                    "id": story.get('id', story_id),
                    "title": story.get('title', 'No title'),
                    "url": story.get('url', ''),
                    "score": story.get('score', None),
                    "comments": story.get('descendants', None),
                    "by": story.get('by', ''),
                    "time": story_time,
                    "text": story.get('text', ''),
                })
            except Exception as e:
                logger.warning("Error processing story %s: %s", story_id, e)
                continue

        return briefs

    def get_best_stories(self):
        story_ids = self.get_best_story_ids()[:self.limit]

        stories = []
        for story_id in story_ids:
            try:
                story = self.get_story_details(story_id)
                if not story:
                    continue
                stories.append(f"{story.get('title', 'No title')} - {story.get('url', '')}")
            except Exception as e:
                logger.warning("Error processing story %s: %s", story_id, e)
                continue
        return stories

def process(user_input, route_data, s):
    try:
        refresh_only = route_data.get('refresh_only', False)
        cache = getattr(s, 'cache', None)
        key = _cache_key()
        try:
            ttl_s = max(1, int(route_data.get('ttl_s', _DEFAULT_TTL_S)))
        except (TypeError, ValueError):
            ttl_s = _DEFAULT_TTL_S
        try:
            max_stale_s = max(1, int(route_data.get('max_stale_s', _DEFAULT_MAX_STALE_S)))
        except (TypeError, ValueError):
            max_stale_s = _DEFAULT_MAX_STALE_S
        if max_stale_s < ttl_s:
            max_stale_s = ttl_s

        # Try serving from cache when not a background refresh
        if not refresh_only and cache is not None:
            try:
                entry = cache.get(key)
                if entry is not None and cache.can_serve(entry):
                    logger.debug("Hacker News cache hit: key=%r", key)
                    return entry.value
            except Exception as e:
                logger.warning("Hacker News cache read failed for key=%r, fetching live data: %s", key, e)

        hacker_news = HackerNews(timeout=s.config.api_timeout)
        briefs = hacker_news.get_best_story_briefs()
        logger.debug("Fetched %d Hacker News stories", len(briefs))

        if not briefs:
            if refresh_only:
                return None
            return "I couldn't fetch any Hacker News stories at the moment. Please try again later."

        extra_info = (
            "Use this information to answer questions about any news. "
            f"This is the hot news at Hacker News at the moment: {str(briefs)}. "
            "Don't read the URLs. "
            "Use your knowledge to give some context to each news item if possible. "
            "Answer the question as if you're on a report news podcast style. "
            "Make sure to include your opinion, but frame it naturally. "
            "Format the text in a natural way to present the news, as if you were telling it to someone you know"
        )

        response = s.ai.generate_response(user_input, extra_info)
        response_text = response.content

        if cache is not None:
            try:
                cache.set(key, response_text, ttl_s=ttl_s, max_stale_s=max_stale_s)
                logger.debug("Hacker News cache updated: key=%r", key)
            except Exception as e:
                logger.warning("Hacker News cache write failed for key=%r: %s", key, e)

        if refresh_only:
            return None

        return response_text
    except Exception as e:
        logger.error("Hacker News plugin error: %s", e)
        if route_data.get('refresh_only', False):
            return None
        return "Unable to fetch Hacker News stories at the moment. Please try again later."
