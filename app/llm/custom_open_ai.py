from typing import Optional

from langchain_core.messages import AIMessageChunk
from langchain_core.outputs.chat_generation import ChatGenerationChunk
from langchain_openai import ChatOpenAI


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

        return generation_chunk
