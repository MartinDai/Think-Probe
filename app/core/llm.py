import random
import time
from pydantic import SecretStr
from typing import Optional

from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs.chat_generation import ChatGenerationChunk
from langchain_openai import ChatOpenAI

from app.config.env_config import get_env_variable
from app.utils.logger import logger


class CustomChatOpenAI(ChatOpenAI):

    def _convert_chunk_to_generation_chunk(
            self,
            chunk: dict,
            default_chunk_class: type,
            base_generation_info: Optional[dict],
    ) -> Optional[ChatGenerationChunk]:

        generation_chunk = super()._convert_chunk_to_generation_chunk(
            chunk,
            default_chunk_class,
            base_generation_info,
        )

        if (choices := chunk.get("choices")) and generation_chunk:
            top = choices[0]
            if isinstance(generation_chunk.message, AIMessageChunk):
                delta = top.get("delta", {})
                reasoning_content = delta.get("reasoning_content")
                if reasoning_content is None:
                    reasoning_content = delta.get("reasoning")

                if reasoning_content is not None:
                    generation_chunk.message.additional_kwargs["reasoning_content"] = reasoning_content

                    if generation_chunk.generation_info is None:
                        generation_chunk.generation_info = {}
                    generation_chunk.generation_info["reasoning_content"] = reasoning_content

        return generation_chunk


RETRYABLE_LLM_ERRORS = (
    InternalServerError,
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
)


# LLM Configuration
API_PATH = get_env_variable("LLM_API_PATH")
API_KEY = get_env_variable("LLM_API_KEY")
MODEL_NAME = get_env_variable("LLM_MODEL_NAME")

logger.info(f"API_PATH: {API_PATH}")
logger.info(f"MODEL_NAME: {MODEL_NAME}")

# Default model instance
DEFAULT_MODEL = CustomChatOpenAI(
    model=MODEL_NAME, 
    base_url=API_PATH,
    api_key=SecretStr(API_KEY),
    temperature=0
)


def invoke_with_retry(model, messages, *, max_attempts: int = 4, base_delay: float = 1.0):
    """
    调用模型并对瞬时性上游错误做有界重试，避免单次 5xx/超时直接中断整个工作流。
    """
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            return model.invoke(messages)
        except RETRYABLE_LLM_ERRORS as exc:
            last_error = exc
            if attempt >= max_attempts:
                break

            sleep_seconds = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.3)
            logger.warning(
                "LLM call failed with %s on attempt %s/%s, retrying in %.2fs: %s",
                exc.__class__.__name__,
                attempt,
                max_attempts,
                sleep_seconds,
                exc,
            )
            time.sleep(sleep_seconds)
        except Exception:
            raise

    raise RuntimeError(
        f"LLM 服务连续失败，已重试 {max_attempts} 次。最后一次错误: {last_error}"
    ) from last_error
