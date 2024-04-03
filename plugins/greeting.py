from common.ai import AI

def process(user_input, route, s):
	ai = AI(s.config)
	side_route = "What's the weather?"
	route = ai.define_route(side_route)
	response = s.route_message(side_route, route)

	return s.ai.generate_response(f"Greet the user (maybe good evening, good night). Casually make a friendly and short comment on the weather. Weather info to consider the answer: {response}").content