import feedparser, datetime

class RSSReader:
    def __init__(self, url, max_items=5):
        self.url = url
        self.max_items = max_items

    def get_latest_news(self):
        news_feed = feedparser.parse(self.url)
        news_items = []
        for entry in news_feed.entries[:self.max_items]:
            news_item = {
                'title': entry.title,
                'link': entry.link,
                'description': entry.description,
                'published': entry.get('published_parsed', None)
            }
            if news_item['published']:
                news_item['published'] = datetime.datetime(*news_item['published'][:6])
            news_items.append(news_item)
        return news_items

def process (user_input, route, s):
    rss_reader = RSSReader(s.config.rss_news, int(s.config.rss_news_max_items))
    latest_news = rss_reader.get_latest_news()
    all_news = []
    for news in latest_news:
        all_news.append(news)
    response = s.ai.generate_response(user_input, f"Use this information to answer questions about any news. Make pertinent comments if any too. This is the hot news at the moment: {str(all_news)}. Don't read the URLs \n. Use your knowledge to give some context to each new if possible")
    return response.content
