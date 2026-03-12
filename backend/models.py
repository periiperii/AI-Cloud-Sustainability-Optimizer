from google import genai

client = genai.Client(api_key="AIzaSyBEYeq4Y4YB61W43IKCYbICpKvhHvv6wYA")

models = client.models.list()

for m in models:
    print(m.name)
