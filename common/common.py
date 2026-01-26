import requests
import logging
from bs4 import BeautifulSoup
from common.error_handling import handle_api_error

class WebTextExtractor:
    def __init__(self, url):
        self.url = url
        self.headers = {
            "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:106.0) Gecko/20100101 Firefox/106.0",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "CallTreeId": "||BTOC-1BF47A0C-CCDD-47BB-A9DA-592009B5FB38",
            "Content-Type": "application/json; charset=UTF-8",
            "x-timeout-ms": "5000",
            "DNT": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin"
            }

    def remove_non_ascii(self, text):
        return ''.join(char for char in text if ord(char) < 128)

    def get_text(self):
        try:
            response = requests.get(self.url, headers=self.headers, timeout=10)
            response.raise_for_status()
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'lxml')
            for script in soup(["script", "style"]):
                script.extract()
            text = soup.get_text()
            text = BeautifulSoup(text, "lxml").text
            text = text.strip().replace("\n", " ").replace("\r", " ").replace("\t", " ")
            cleaned_result = self.remove_non_ascii(text)
            return cleaned_result
        except requests.exceptions.RequestException as e:
            error_msg = handle_api_error(e, service_name=f"Web fetch ({self.url})")
            logging.error(f"Web text extraction error: {e}")
            print(error_msg)
            return f"Error fetching content from {self.url}"
        except Exception as e:
            error_msg = f"Error parsing web content: {str(e)}"
            logging.error(f"Web text parsing error: {e}")
            print(f"Error: {error_msg}")
            return "Error parsing web content"
