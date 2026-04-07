import feedparser, datetime, logging

logger = logging.getLogger(__name__)

_DEFAULT_TTL_S = 7200       # 2 hours
_DEFAULT_MAX_STALE_S = 14400  # 4 hours


def _cache_key(rss_url):
    return f"news:{rss_url}"


class RSSReader:
    def __init__(self, url, max_items=5):
        self.url = url
        self.max_items = max_items

    def get_latest_news(self):
        try:
            news_feed = feedparser.parse(self.url)

            # Check if feed was successfully parsed
            if hasattr(news_feed, 'bozo_exception') and news_feed.bozo_exception:
                raise news_feed.bozo_exception

            news_items = []
            for entry in news_feed.entries[:self.max_items]:
                try:
                    news_item = {
                        'title': entry.get('title', 'No title'),
                        'link': entry.get('link', ''),
                        'description': entry.get('description', ''),
                        'published': entry.get('published_parsed', None)
                    }
                    if news_item['published']:
                        news_item['published'] = datetime.datetime(*news_item['published'][:6])
                    news_items.append(news_item)
                except Exception as e:
                    logger.warning("Error parsing news entry: %s", e)
                    continue

            return news_items
        except Exception as e:
            logger.error("RSS feed error: %s", e)
            return []

def process(user_input, route, s):
    try:
        rss_url = route.get('rss_url') or s.config.rss_news
        refresh_only = route.get('refresh_only', False)
        cache = getattr(s, 'cache', None)
        key = _cache_key(rss_url)
        ttl_s = route.get('ttl_s', _DEFAULT_TTL_S)
        max_stale_s = route.get('max_stale_s', _DEFAULT_MAX_STALE_S)

        # Try serving from cache when not a background refresh
        if not refresh_only and cache is not None:
            try:
                entry = cache.get(key)
                if entry is not None and cache.can_serve(entry):
                    logger.debug("News cache hit: key=%r", key)
                    return entry.value
            except Exception as e:
                logger.warning("News cache read failed for key=%r, fetching live data: %s", key, e)

        rss_reader = RSSReader(rss_url, int(s.config.rss_news_max_items))
        latest_news = rss_reader.get_latest_news()

        if not latest_news:
            if refresh_only:
                return None
            return "I couldn't fetch any news at the moment. Please try again later."

        response = s.ai.generate_response(user_input, f"Use this information to answer questions about any news. Make pertinent comments if any too. This is the hot news at the moment: {str(latest_news)}. Don't read the URLs \n. Use your knowledge to give some context to each news item if possible")
        response_text = response.content

        if cache is not None:
            try:
                cache.set(key, response_text, ttl_s=ttl_s, max_stale_s=max_stale_s)
                logger.debug("News cache updated: key=%r", key)
            except Exception as e:
                logger.warning("News cache write failed for key=%r: %s", key, e)

        if refresh_only:
            return None

        return response_text
    except Exception as e:
        logger.error("News plugin error: %s", e)
        if route.get('refresh_only', False):
            return None
        return "Unable to fetch news at the moment. Please try again later."
