import requests
from common.common import WebTextExtractor

class HackerNews:
    def __init__(self):
        self.base_url = "https://hacker-news.firebaseio.com/v0/"
        self.limit = 5

    def get_best_story_ids(self):
        response = requests.get(self.base_url + "beststories.json")
        return response.json()

    def get_story_details(self, story_id):
        response = requests.get(self.base_url + f"item/{story_id}.json")
        return response.json()

    def get_best_stories_summary(self):
        summaries = []
        story_ids = self.get_best_story_ids()[:self.limit]
        for story_id in story_ids:
            story = self.get_story_details(story_id)
            extractor = WebTextExtractor(story['url'])
            text = extractor.get_text()
            summaries.append({"title": story['title'], "text": text})
        return summaries

    def get_best_stories(self):
        story_ids = self.get_best_story_ids()[:self.limit]

        stories = []
        for story_id in story_ids:
            story = self.get_story_details(story_id)
            stories.append(f"{story['title']} - {story['url']}")
        return stories

def process(user_input, route_data, s):
    hacker_news = HackerNews()
    stories = hacker_news.get_best_stories_summary()
    all_stories = []
    for story in stories:
        summary = s.ai.text_summary(story['text'], words=s.config.summary_words)
        all_stories.append(f"{story['title']} - {summary}")
    response = s.ai.generate_response(user_input, f"Use this information to answer questions about any news. This is the hot news at Hacker News at the moment: {str(all_stories)}. Don't read the URLs \n. Use your knowledge to give some context to each new if possible. Answer the question as if you're on a report news podcast style. Make sure to include the take away for each news. Make sure to include your opinion.")
    return response.content