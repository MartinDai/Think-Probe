import json
import logging

from langchain_core.messages import HumanMessage

from app.context.conversation_context import ConversationContext
from app.model import MODEL_NAME
from app.node import Agent
from app.node.workflow import run_agent_stream
from app.node.triage_agent import triage_agent
from app.node.shell_agent import get_shell_agent
from app.node.java_diagnosis_agent import java_diagnosis_agent
from app.service import conversation_service
from app.utils import response_util


async def get_agent(agent_name: str) -> Agent:
    """Get agent instance by name"""
    if agent_name == "shell":
        return await get_shell_agent()
    elif agent_name == "java_diagnosis":
        return java_diagnosis_agent
    else:
        return triage_agent


async def process_message(message: str, context: ConversationContext):
    conversation_id = context.conversation_id
    messages = context.messages
    messages.append(HumanMessage(content=message))

    agent = await get_agent(context.current_agent)

    async for event in run_agent_stream(agent, messages):
        event_type = event["type"]

        if event_type == "text_delta":
            response_chunk = response_util.create_chunk(
                conversation_id=conversation_id,
                content=event["content"],
                role="assistant",
                model=MODEL_NAME,
            )
            yield f"data: {json.dumps(response_chunk)}\n\n"

        elif event_type == "tool_start":
            content = f"执行工具调用: {event['name']} 输入:\n{json.dumps(event['args'], ensure_ascii=False, indent=2)}"
            logging.info(content)
            response_chunk = response_util.create_chunk(
                conversation_id=conversation_id,
                content=content,
                role="assistant",
                model=MODEL_NAME,
            )
            yield f"data: {json.dumps(response_chunk)}\n\n"

        elif event_type == "tool_end":
            content = f"工具执行完成: {event['name']} 输出:\n{event['result']}"
            logging.info(content)
            response_chunk = response_util.create_chunk(
                conversation_id=conversation_id,
                content=content,
                role="assistant",
                model=MODEL_NAME,
            )
            yield f"data: {json.dumps(response_chunk)}\n\n"

        elif event_type == "step_done":
            yield f"data: {json.dumps(response_util.create_step_done(conversation_id))}\n\n"

        elif event_type == "error":
            content = f"错误: {event['message']}"
            logging.error(content)
            response_chunk = response_util.create_chunk(
                conversation_id=conversation_id,
                content=content,
                role="assistant",
                model=MODEL_NAME,
            )
            yield f"data: {json.dumps(response_chunk)}\n\n"

        elif event_type == "final":
            yield f"data: {json.dumps(response_util.create_step_done(conversation_id))}\n\n"

    conversation_service.save_conversation(context)
