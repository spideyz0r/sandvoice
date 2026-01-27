def process(user_input, route_data, s):
    background_story = "You are a tech guru and a teacher. Be very didactic and explain the concepts in an easy way to grasp. Give examples if the question is not very trivial." 
    response = s.ai.generate_response(user_input, background_story, "gpt-4")
    return response.content
