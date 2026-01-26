import requests, logging
from common.common import WebTextExtractor
from common.error_handling import handle_api_error

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
            error_msg = handle_api_error(e, service_name="Hacker News API")
            logging.error(f"Hacker News API error: {e}")
            print(error_msg)
            return []

    def get_story_details(self, story_id):
        try:
            response = requests.get(self.base_url + f"item/{story_id}.json", timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_msg = handle_api_error(e, service_name="Hacker News API")
            logging.error(f"Hacker News story error: {e}")
            print(error_msg)
            return None

    def get_best_stories_summary(self):
        summaries = []
        story_ids = self.get_best_story_ids()[:self.limit]
        for story_id in story_ids:
            try:
                story = self.get_story_details(story_id)
                if not story or 'url' not in story:
                    continue
                extractor = WebTextExtractor(story['url'], timeout=self.timeout)
                text = extractor.get_text()
                summaries.append({"title": story.get('title', 'No title'), "text": text})
            except Exception as e:
                logging.error(f"Error processing story {story_id}: {e}")
                continue
        return summaries

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
                logging.error(f"Error processing story {story_id}: {e}")
                continue
        return stories

def process(user_input, route_data, s):
    hacker_news = HackerNews(timeout=s.config.api_timeout)
    stories = hacker_news.get_best_stories_summary()
    all_stories = []
    for story in stories:
        summary = s.ai.text_summary(story['text'], words=s.config.summary_words)
        all_stories.append(f"{story['title']} - {summary}")
    response = s.ai.generate_response(user_input, f"Use this information to answer questions about any news. This is the hot news at Hacker News at the moment: {str(all_stories)}. Don't read the URLs \n. Use your knowledge to give some context to each new if possible. Answer the question as if you're on a report news podcast style. Make sure to include the take away for each news. Make sure to include your opinion.")
    return response.content