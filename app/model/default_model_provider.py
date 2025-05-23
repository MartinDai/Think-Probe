from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.model import MODEL_NAME, API_KEY, API_PATH

DEFAULT_MODEL = ChatOpenAI(model=MODEL_NAME, base_url=API_PATH,
                           api_key=SecretStr(API_KEY),
                           temperature=0)
