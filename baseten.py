import os

try:
    from openai import OpenAI
except ImportError:
    raise SystemExit(
        "baseten.py needs the optional 'openai' package "
        "(pip install openai) — it is not a pipeline dependency.")

api_key = os.environ.get("BASETEN_API_KEY")
if not api_key:
    raise SystemExit("BASETEN_API_KEY is not set — export it before running.")

client = OpenAI(
    base_url="https://inference.baseten.co/v1",
    api_key=api_key,
)

response = client.chat.completions.create(
    model="meta-models/muse-spark-open-1026",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
