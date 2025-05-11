from agents import ModelProvider, OpenAIChatCompletionsModel, Model
from openai import AsyncOpenAI

from app.model import MODEL_NAME, API_KEY, API_PATH


class DefaultModelProvider(ModelProvider):
    def get_model(self, model_name: str | None) -> Model:
        return OpenAIChatCompletionsModel(model=MODEL_NAME,
                                          openai_client=AsyncOpenAI(base_url=API_PATH,
                                                                    api_key=API_KEY))


MODEL_PROVIDER = DefaultModelProvider()
