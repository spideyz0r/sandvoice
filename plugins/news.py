import feedparser, datetime, logging

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
                    logging.error(f"Error parsing news entry: {e}")
                    continue

            return news_items
        except Exception as e:
            error_msg = f"Error fetching RSS feed: {str(e)}"
            logging.error(f"RSS feed error: {e}")
            print(f"Error: {error_msg}")
            return []

def process (user_input, route, s):
    rss_reader = RSSReader(s.config.rss_news, int(s.config.rss_news_max_items))
    latest_news = rss_reader.get_latest_news()
    all_news = []
    for news in latest_news:
        all_news.append(news)
    response = s.ai.generate_response(user_input, f"Use this information to answer questions about any news. Make pertinent comments if any too. This is the hot news at the moment: {str(all_news)}. Don't read the URLs \n. Use your knowledge to give some context to each new if possible")
    return response.content
