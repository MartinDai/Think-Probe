from app.config import env_config
from app.utils.logger import logger

API_PATH = env_config.get_env_variable("LLM_API_PATH")
API_KEY = env_config.get_env_variable("LLM_API_KEY")
MODEL_NAME = env_config.get_env_variable("LLM_MODEL_NAME")

logger.info(f"API_PATH:{API_PATH}")
logger.info(f"API_KEY:{API_KEY}")
logger.info(f"MODEL_NAME:{MODEL_NAME}")
