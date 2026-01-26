
import googlesearch, requests, logging
from common.common import WebTextExtractor

class GoogleSearcher:
    def __init__(self, num_results=3):
        self.num_results = num_results

    def search(self, query):
        try:
            print (f"Searching for {query}, getting {self.num_results} results.")
            results = googlesearch.search(query, num_results=self.num_results)
            return list(results)
        except Exception as e:
            error_msg = f"Search error: {str(e)}"
            logging.error(f"Google search error: {e}")
            print(f"Error: {error_msg}")
            return []

def process(user_input, route, s):
    try:
        if s.config.debug:
            print(f"Searching for real time information using {s.config.search_sources} sources.")
        searcher = GoogleSearcher(int(s.config.search_sources))
        if not route.get('query'):
            route['query'] = user_input
        results = searcher.search(route['query'])

        if not results:
            return "I couldn't find any search results. Please try again later."

        summaries = []
        if s.config.debug:
            print("Results" + str(results) + "\n\n")
        for r in results:
            try:
                if s.config.debug:
                    print(f"Extracting text from {r}")
                extractor = WebTextExtractor(r)
                text = extractor.get_text()
                summary = s.ai.text_summary(text, route['query'], words=s.config.summary_words)
                summaries.append({"text": summary})
            except Exception as e:
                logging.error(f"Error processing search result {r}: {e}")
                continue

        if not summaries:
            return "I couldn't extract information from the search results. Please try again."

        if s.config.debug:
            print ("Summaries" + str(summaries) + "\n\n")
        response = s.ai.generate_response(user_input, f"You have access to an Internet search to look for real data information. You must answer the question. This is the contex information to answer the question: {str(summaries)}\n")
        return response.content
    except Exception as e:
        error_msg = f"Real-time search error: {str(e)}"
        logging.error(f"Real-time search processing error: {e}")
        print(f"Error: {error_msg}")
        return "I encountered an error while searching for information. Please try again."
