import json
import logging

from langchain_core.messages import HumanMessage

from app.context.conversation_context import ConversationContext
from app.model import MODEL_NAME
from app.node import NodeState, workflow
from app.service import conversation_service
from app.utils import response_util


async def process_message(message: str, context: ConversationContext):
    conversation_id = context.conversation_id
    messages = context.messages
    messages.append(HumanMessage(content=message))

    graph = await workflow.build_graph(context.current_node)
    initial_state = NodeState(messages=messages, current=context.current_node, remaining_steps=10)
    async for event in graph.astream_events(input=initial_state):
        if event["event"] == "on_tool_start":
            tool_name = event["name"]
            content = f"执行工具调用: {tool_name} 输入:\n{json.dumps(event["data"]["input"], ensure_ascii=False, indent=2)}"
            logging.info(content)
            if not tool_name.startswith("transfer_to_"):
                response_chunk = response_util.create_chunk(conversation_id=conversation_id,
                                                            content=content,
                                                            role="assistant", model=MODEL_NAME)
                yield f"data: {json.dumps(response_chunk)}\n\n"
                yield f"data: {json.dumps(response_util.create_step_done(conversation_id))}\n\n"
        elif event["event"] == "on_chain_stream":
            event_name = event["name"]
            if event_name == "tools":
                tool_messages = event["data"]["chunk"]["messages"]
                for tool_message in tool_messages:
                    content = f"工具执行完成: {tool_message.name} 输出:\n{json.dumps(tool_message.content, ensure_ascii=False, indent=2)}"
                    logging.info(content)
                    if tool_message.name.startswith("transfer_to_"):
                        context.current_node = tool_message.content
                    else:
                        messages.append(tool_message)
                        response_chunk = response_util.create_chunk(conversation_id=conversation_id,
                                                                    content=content,
                                                                    role="assistant", model=MODEL_NAME)
                        yield f"data: {json.dumps(response_chunk)}\n\n"
                        yield f"data: {json.dumps(response_util.create_step_done(conversation_id))}\n\n"
        elif event["event"] == "on_chat_model_stream":
            content = event["data"]["chunk"].content
            if content:
                response_chunk = response_util.create_chunk(conversation_id=conversation_id,
                                                            content=content,
                                                            role="assistant", model=MODEL_NAME)
                yield f"data: {json.dumps(response_chunk)}\n\n"
        elif event["event"] == "on_chat_model_end":
            tool_calls = event["data"]["output"].tool_calls
            if not tool_calls or not tool_calls[0]["name"].startswith("transfer_to_"):
                messages.append(event["data"]["output"])
                yield f"data: {json.dumps(response_util.create_step_done(conversation_id))}\n\n"
        else:
            pass
            logging.info(f"event: {json.dumps(event, default=str, ensure_ascii=False)}")

    conversation_service.save_conversation(context)
