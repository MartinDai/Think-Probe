import json

from agents import trace, Runner, RunConfig, ItemHelpers
from openai.types.responses import EasyInputMessageParam, ResponseTextDeltaEvent

from app.config.env_config import on_debug
from app.context.conversation_context import ConversationContext
from app.model import MODEL_NAME
from app.model.default_model_provider import MODEL_PROVIDER
from app.service import conversation_service
from app.utils.logger import logger
from app.utils.response_util import create_chunk, create_step_done


async def process_message(message: str, context_manager: ConversationContext):
    conversation_id = context_manager.conversation_id
    with trace("think-probe", group_id=conversation_id):
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
                    final_chunk = create_chunk(conversation_id=conversation_id,
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
                        chunk = create_chunk(conversation_id=conversation_id,
                                             content=content,
                                             role="tool",
                                             model=MODEL_NAME)
                        yield f"data: {json.dumps(chunk)}\n\n"
                        yield f"data: {json.dumps(create_step_done(conversation_id=conversation_id))}\n\n"
                elif event.item.type == "tool_call_output_item":
                    content = f"工具输出：{event.item.output}"
                    logger.info(content)
                    if on_debug:
                        chunk = create_chunk(conversation_id=conversation_id,
                                             content=content,
                                             role="tool",
                                             model=MODEL_NAME)
                        yield f"data: {json.dumps(chunk)}\n\n"
                        yield f"data: {json.dumps(create_step_done(conversation_id=conversation_id))}\n\n"
                elif event.item.type == "message_output_item":
                    logger.info(f"AI: {ItemHelpers.text_message_output(event.item)}")
                else:
                    continue
            else:
                continue

        # 发送结束标记
        yield f"data: {json.dumps(create_step_done(conversation_id=conversation_id))}\n\n"

        # 更新上下文
        context_manager.input_items = result.to_input_list()
        context_manager.current_agent = result.last_agent
        conversation_service.save_conversation(context_manager)
