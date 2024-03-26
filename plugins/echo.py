class Echo:
	def echo_back(self, user_input):
		return user_input
def process(user_input, route_data, s):
	e = Echo()
	return e.echo_back(user_input)