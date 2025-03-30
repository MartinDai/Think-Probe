from agents import ModelProvider, OpenAIChatCompletionsModel, Model
from openai import AsyncOpenAI

from app.config.config import config

BASE_URL = config.get("base_url")
API_KEY = config.get("api_key")

custom_client = AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)

MODEL_NAME = config.get("model_name")

class CustomModelProvider(ModelProvider):
    def get_model(self, model_name: str | None) -> Model:
        return OpenAIChatCompletionsModel(model=MODEL_NAME, openai_client=custom_client)


MODEL_PROVIDER = CustomModelProvider()
