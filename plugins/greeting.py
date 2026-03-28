from common.plugin_loader import build_extra_routes_text

def process(user_input, route, s):
	side_route = "What's the weather?"
	manifests = getattr(s, '_plugin_manifests', [])
	extra_routes = build_extra_routes_text(manifests, location=s.config.location)
	weather_route = s.ai.define_route(side_route, extra_routes=extra_routes)
	response = s.route_message(side_route, weather_route)
	extra_system = f"""
	Greet the user! You are very friendly.
	Depending on the current date and time use good evening/afternoon/morning match the greeting with the time.
	Casually make a friendly and short comment on the weather. Weather info to consider the answer: {response}
	Considering the current day and time, make a fun fact comment about today or this month.
	"""
	return s.ai.generate_response(user_input, extra_system).content
