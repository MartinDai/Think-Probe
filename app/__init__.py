from agents import set_default_openai_key

from app.config.config import config

OPENAI_API_KEY = config.get("openai_api_key")
set_default_openai_key(OPENAI_API_KEY)
