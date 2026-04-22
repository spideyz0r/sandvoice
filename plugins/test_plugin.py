def process(user_input, route, s):
    data = fetch_data(user_input)
    result = data['value']
    return result

def fetch_data(query):
    import requests
    r = requests.get(f"https://api.example.com/data?q={query}")
    return r.json()
