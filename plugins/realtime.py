
import googlesearch, requests
from common.common import WebTextExtractor

class GoogleSearcher:
    def __init__(self, num_results=3):
        self.num_results = num_results

    def search(self, query):
        print (f"Searching for {query}, getting {self.num_results} results.")
        results = googlesearch.search(query, num_results=self.num_results)
        return list(results)

def process(user_input, route, s):
    if s.config.debug:
        print(f"Searching for real time information using {s.config.search_sources} sources.")
    searcher = GoogleSearcher(int(s.config.search_sources))
    if not route.get('query'):
        route['query'] = user_input
    results = searcher.search(route['query'])
    summaries = []
    if s.config.debug:
        print("Results" + str(results) + "\n\n")
    for r in results:
        if s.config.debug:
            print(f"Extracting text from {r}")
        extractor = WebTextExtractor(r)
        text = extractor.get_text()
        summary = s.text_summary(text, route['query'], words=s.config.summary_words)
        summaries.append({"text": summary})
    if s.config.debug:
        print ("Summaries" + str(summaries) + "\n\n")
    response = s.generate_response(user_input, f"You have access to an Internet search to look for real data information. You must answer the question. This is the contex information to answer the question: {str(summaries)}\n")
    return response.content
