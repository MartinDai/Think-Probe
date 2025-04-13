import json
from typing import Dict

from agents import trace, Runner, RunConfig, ItemHelpers
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from openai.types.responses import ResponseTextDeltaEvent, EasyInputMessageParam

from app import conversation
from app.config.config import on_debug
from app.context.conversation_context import ConversationContext
from app.model.default_model import MODEL_PROVIDER, MODEL_NAME
from app.utils.logger import logger
from app.utils.response_util import create_chunk, create_block


async def process_message(message: str, context_manager: ConversationContext):
    with trace("think-probe", group_id=context_manager.conversation_id):
        context_manager.input_items.append(EasyInputMessageParam(content=message, role="user"))
        result = Runner.run_streamed(
            context_manager.current_agent,
            context_manager.input_items,
            context=context_manager.context,
            run_config=RunConfig(model_provider=MODEL_PROVIDER)
        )

        async for event in result.stream_events():
            if event.type == "raw_response_event":
                if isinstance(event.data, ResponseTextDeltaEvent):
                    final_chunk = create_chunk(conversation_id=context_manager.conversation_id,
                                               content=event.data.delta,
                                               role="assistant", model=MODEL_NAME)
                    yield f"data: {json.dumps(final_chunk)}\n\n"
                else:
                    continue
            elif event.type == "agent_updated_stream_event":
                logger.info(f"Handed off to {event.new_agent.name}")
            elif event.type == "run_item_stream_event":
                if event.item.type == "tool_call_item":
                    content = f"调用工具：{event.item.raw_item.name}，参数：{event.item.raw_item.arguments}"
                    logger.info(content)
                    if on_debug:
                        block = create_block(conversation_id=context_manager.conversation_id,
                                             content=content,
                                             role="tool",
                                             model=MODEL_NAME)
                        yield f"data: {json.dumps(block)}\n\n"
                elif event.item.type == "tool_call_output_item":
                    content = f"工具输出：{event.item.output}"
                    logger.info(content)
                    if on_debug:
                        block = create_block(conversation_id=context_manager.conversation_id,
                                             content=content,
                                             role="tool",
                                             model=MODEL_NAME)
                        yield f"data: {json.dumps(block)}\n\n"
                elif event.item.type == "message_output_item":
                    logger.info(f"AI: {ItemHelpers.text_message_output(event.item)}")
                else:
                    continue
            else:
                continue

        # 发送结束标记
        yield f"data: [DONE]\n\n"

        # 更新上下文
        context_manager.input_items = result.to_input_list()
        context_manager.current_agent = result.last_agent
        conversation.save_conversation(context_manager)


conversation_contexts: Dict[str, ConversationContext] = {}

chat_completions_router = APIRouter(prefix="")


@chat_completions_router.post("/v1/chat/completions")
async def chat_completion(request: Request):
    data = await request.json()
    conversation_id = data.get("conversation_id", "")
    message = data.get("messages", [{}])[-1].get("content", "")

    conversation_context = conversation.find_conversation(conversation_id)
    if conversation_context is None:
        conversation_context = ConversationContext(conversation_id)
    return StreamingResponse(process_message(message, conversation_context), media_type="text/event-stream")
