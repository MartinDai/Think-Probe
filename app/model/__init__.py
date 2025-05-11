from agents import set_default_openai_api, set_default_openai_key

from app.config import env_config
from app.utils.logger import logger

API_PATH = env_config.get_env_variable("LLM_API_PATH")
API_KEY = env_config.get_env_variable("LLM_API_KEY")
MODEL_NAME = env_config.get_env_variable("LLM_MODEL_NAME")

logger.info(f"API_PATH:{API_PATH}")
logger.info(f"API_KEY:{API_KEY}")
logger.info(f"MODEL_NAME:{MODEL_NAME}")

set_default_openai_api("chat_completions")

OPENAI_API_KEY = env_config.get_env_variable("OPENAI_API_KEY")
set_default_openai_key(OPENAI_API_KEY)
