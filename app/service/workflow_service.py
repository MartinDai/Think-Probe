import json
import logging

from langchain_core.messages import HumanMessage
from langfuse import get_client

from app.context.conversation_context import ConversationContext
from app.core.llm import MODEL_NAME
from app.agents.base import Agent
from app.agents.runner import run_agent_stream
from app.agents.orchestrator import orchestrator_agent
from app.agents.java_expert import java_expert_agent
from app.service import conversation_service
from app.utils import response_util


async def get_main_agent() -> Agent:
    """Build the main agent with all sub-agents wired up"""
    return Agent(
        name=orchestrator_agent.name,
        instructions=orchestrator_agent.instructions,
        tools=orchestrator_agent.tools,
        sub_agents=[java_expert_agent],
    )


async def process_message(message: str, context: ConversationContext):
    conversation_id = context.conversation_id
    messages = context.messages

    # Append user message and persist to orchestrator's JSONL
    user_msg = HumanMessage(content=message)
    messages.append(user_msg)
    conversation_service.append_message(conversation_id, "orchestrator", user_msg)

    agent = await get_main_agent()

    langfuse_client = get_client()
    trace_name = message[:50] if message else "Chat Interaction"
    
    with langfuse_client.start_as_current_observation(name=trace_name) as trace:
        async for event in run_agent_stream(agent, messages, session_id=conversation_id):
            event_type = event["type"]

            if event_type == "thought_delta":
                response_chunk = response_util.create_chunk(
                    conversation_id=conversation_id,
                    reasoning_content=event["content"],
                    role="assistant",
                    model=MODEL_NAME,
                )
                yield f"data: {json.dumps(response_chunk)}\n\n"

            elif event_type == "text_delta":
                response_chunk = response_util.create_chunk(
                    conversation_id=conversation_id,
                    content=event["content"],
                    role="assistant",
                    model=MODEL_NAME,
                )
                yield f"data: {json.dumps(response_chunk)}\n\n"

            elif event_type == "tool_start":
                logging.info(f"Tool start: {event['name']}")
                response_chunk = response_util.create_chunk(
                    conversation_id=conversation_id,
                    role="assistant",
                    model=MODEL_NAME,
                )
                response_chunk["choices"][0]["delta"]["tool_start"] = {
                    "name": event["name"],
                    "args": event["args"]
                }
                yield f"data: {json.dumps(response_chunk)}\n\n"

            elif event_type == "tool_end":
                logging.info(f"Tool end: {event['name']}")
                response_chunk = response_util.create_chunk(
                    conversation_id=conversation_id,
                    role="assistant",
                    model=MODEL_NAME,
                )
                response_chunk["choices"][0]["delta"]["tool_end"] = {
                    "name": event["name"],
                    "result": event["result"]
                }
                yield f"data: {json.dumps(response_chunk)}\n\n"

            elif event_type == "sub_agent_start":
                logging.info(f"Sub-agent start: {event['name']}")
                response_chunk = response_util.create_chunk(
                    conversation_id=conversation_id,
                    role="assistant",
                    model=MODEL_NAME,
                )
                response_chunk["choices"][0]["delta"]["sub_agent_start"] = {
                    "name": event["name"],
                    "task": event["task"]
                }
                yield f"data: {json.dumps(response_chunk)}\n\n"

            elif event_type == "sub_agent_end":
                logging.info(f"Sub-agent end: {event['name']}")
                response_chunk = response_util.create_chunk(
                    conversation_id=conversation_id,
                    role="assistant",
                    model=MODEL_NAME,
                )
                response_chunk["choices"][0]["delta"]["sub_agent_end"] = {
                    "name": event["name"],
                    "result": event["result"]
                }
                yield f"data: {json.dumps(response_chunk)}\n\n"

            elif event_type == "message_persist":
                # Incremental JSONL persistence — write to the correct agent's file
                conversation_service.append_message(
                    conversation_id, event["agent"], event["message"],
                    extra=event.get("extra"),
                )

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
