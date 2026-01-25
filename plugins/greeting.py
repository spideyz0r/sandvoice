from common.ai import AI

def process(user_input, route, s):
	ai = AI(s.config)
	side_route = "What's the weather?"
	route = ai.define_route(side_route)
	response = s.route_message(side_route, route)
	extra_system = f"""
	Greet the user! You are very friendly.
	Depending on the current date and time use good evening/afternoon/moring match the greeting with the time.
	Casually make a friendly and short comment on the weather. Weather info to consider the answer: {response}").content
	Considering the current day and time, make a fun fact comment about today or this month.
	"""

	return s.ai.generate_response(user_input, extra_system).content
