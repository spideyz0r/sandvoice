import os, requests, logging
from common.error_handling import handle_api_error

class OpenWeatherReader:
    def __init__(self, location, unit = "metric", timeout = 10):
        if not os.environ.get('OPENWEATHERMAP_API_KEY'):
            error_msg = "Missing OPENWEATHERMAP_API_KEY environment variable"
            print(f"Error: {error_msg}")
            raise ValueError(error_msg)
        self.api_key = os.environ['OPENWEATHERMAP_API_KEY']
        self.location = location
        self.unit = unit
        self.timeout = timeout
        self.base_url = "https://api.openweathermap.org/data/2.5/weather?"

    def get_current_weather(self):
        try:
            url = f"{self.base_url}q={self.location}&appid={self.api_key}&units={self.unit}"
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            # not formating the output, since the model can understand that
            return response.json()
        except requests.exceptions.RequestException as e:
            error_msg = handle_api_error(e, service_name="OpenWeatherMap")
            logging.error(f"Weather API error: {e}")
            print(error_msg)
            return {"error": "Unable to fetch weather data"}
        except Exception as e:
            error_msg = f"Weather service error: {str(e)}"
            logging.error(f"Weather error: {e}")
            print(f"Error: {error_msg}")
            return {"error": "Weather service unavailable"}

def process(user_input, route, s):
    try:
        if not route.get('location'):
            if s.config.debug:
                print("No location found in route, using default location")
            route['location'] = s.config.location
        if not route.get('unit'):
            if s.config.debug:
                print("No unit found in route, using default unit")
            route['unit'] =  s.config.unit

        weather = OpenWeatherReader(route['location'], route['unit'], s.config.api_timeout)
        current_weather = weather.get_current_weather()
        response = s.ai.generate_response(user_input, f"You can answer questions about weather. This is the information of the weather the user asked: {str(current_weather)}\n")
        return response.content
    except ValueError as e:
        error_msg = f"Weather service configuration error: {str(e)}"
        if s.config.debug:
            logging.error(f"Weather plugin error: {e}")
        return "Unable to fetch weather information. Please check your configuration."
    except Exception as e:
        error_msg = f"Weather service error: {str(e)}"
        if s.config.debug:
            logging.error(f"Weather plugin error: {e}")
        return "Unable to fetch weather information. Please try again later."
