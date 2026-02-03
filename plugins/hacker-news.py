import requests, logging, datetime
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
                logging.error(f"Error processing story {story_id}: {e}")
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
                logging.error(f"Error processing story {story_id}: {e}")
                continue
        return stories

def process(user_input, route_data, s):
    try:
        hacker_news = HackerNews(timeout=s.config.api_timeout)
        briefs = hacker_news.get_best_story_briefs()
        if s.config.debug:
            print(f"Fetched {len(briefs)} Hacker News stories")

        if not briefs:
            return "I couldn't fetch any Hacker News stories at the moment. Please try again later."

        extra_info = (
            "Use this information to answer questions about any news. "
            f"This is the hot news at Hacker News at the moment: {str(briefs)}. "
            "Don't read the URLs. "
            "Use your knowledge to give some context to each news item if possible. "
            "Answer the question as if you're on a report news podcast style. "
            "Make sure to include the take away for each news. "
            "Make sure to include your opinion."
        )

        response = s.ai.generate_response(user_input, extra_info)
        return response.content
    except Exception as e:
        if s.config.debug:
            logging.error(f"Hacker News plugin error: {e}")
        return "Unable to fetch Hacker News stories at the moment. Please try again later."
