import os, requests

class OpenWeatherReader:
    def __init__(self, location, unit = "metric"):
        self.api_key = os.environ['OPENWEATHERMAP_API_KEY']
        self.location = location
        self.unit = unit
        self.base_url = "https://api.openweathermap.org/data/2.5/weather?"

    def get_current_weather(self):
        url = f"{self.base_url}q={self.location}&appid={self.api_key}&units={self.unit}"
        response = requests.get(url)

        if response.status_code == 200:
            # not formating the output, since the model can understand that
            return response.json()
        else:
            return None

def process(user_input, route, s):
    if not route.get('location'):
        if s.config.debug:
            print("No location found in route, using default location")
        route['location'] = s.config.location
    if not route.get('unit'):
        if s.config.debug:
            print("No unit found in route, using default unit")
        route['unit'] =  s.config.unit
    weather = OpenWeatherReader(route['location'], route['unit'])
    current_weather = weather.get_current_weather()
    response = s.ai.generate_response(user_input, f"You can answer questions about weather. This is the information of the weather the user asked: {str(current_weather)}\n")
    return response.content
