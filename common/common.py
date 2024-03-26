import requests
from bs4 import BeautifulSoup

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
        response = requests.get(self.url, headers=self.headers)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'lxml')
        for script in soup(["script", "style"]):
            script.extract()
        text = soup.get_text()
        text = BeautifulSoup(text, "lxml").text
        text = text.strip().replace("\n", " ").replace("\r", " ").replace("\t", " ")
        cleaned_result = self.remove_non_ascii(text)
        return cleaned_result
