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
    background_story = "You are a tech guru and a teacher. Be very didactic and explain the concepts in an eay way to grap. Give examples if the question is not very trivial." 
    response = s.ai.generate_response(user_input, background_story, "gpt-4")
    return response.content
