import asyncio
from datetime import datetime
import os
from typing import List, Dict, Any, AsyncGenerator

from langchain_core.messages import BaseMessage, AIMessage, ToolMessage, SystemMessage, HumanMessage
from langchain_core.tools import StructuredTool
from langfuse.langchain import CallbackHandler

from app.agents.base import Agent
from app.core.llm import DEFAULT_MODEL
from app.schemas.agent import SubAgentInput
from app.utils.logger import logger
from app.config.env_config import get_env_variable


# Langfuse configuration
langfuse_secret = get_env_variable("LANGFUSE_SECRET_KEY")
langfuse_public = get_env_variable("LANGFUSE_PUBLIC_KEY")
langfuse_host = get_env_variable("LANGFUSE_BASE_URL") or get_env_variable("LANGFUSE_HOST")
if langfuse_host and "LANGFUSE_HOST" not in os.environ:
    os.environ["LANGFUSE_HOST"] = langfuse_host


class MaxTurnsExceeded(Exception):
    """Raised when an agent loop exceeds the maximum number of turns."""
    pass


def _create_sub_agent_tool(sub_agent: Agent) -> StructuredTool:
    """
    Create a tool definition for delegating tasks to a sub-agent.
    """
    def _placeholder(task: str) -> str:
        return ""

    return StructuredTool(
        name=f"transfer_to_{sub_agent.name}",
        description=(
            f"委派任务给 '{sub_agent.name}' 子代理。 "
            f"该子代理的能力范围：{sub_agent.instructions[:200]}"
        ),
        func=_placeholder,
        args_schema=SubAgentInput,
    )


async def run_agent_stream(
    agent: Agent, 
    messages: List[BaseMessage], 
    max_turns: int = 10, 
    persist_key: str = None, 
    session_id: str = None,
    stop_event: asyncio.Event = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Core agent loop - Multi-agent collaboration with tool calling support.
    """
    _persist_key = persist_key or agent.name
    system_message = SystemMessage(content=agent.instructions)

    # Build sub-agent map and tools
    sub_agent_map = {f"transfer_to_{sa.name}": sa for sa in agent.sub_agents}
    sub_agent_tools = [_create_sub_agent_tool(sa) for sa in agent.sub_agents]

    # Combine regular tools + sub-agent delegation tools
    all_tools = agent.tools + sub_agent_tools

    model = DEFAULT_MODEL
    if all_tools:
        model = model.bind_tools(all_tools)

    callbacks = []
    run_config = None
    if langfuse_secret and langfuse_public:
        handler = CallbackHandler()
        callbacks.append(handler)
        
        run_config = {
            "callbacks": callbacks,
            "metadata": {
                "langfuse_session_id": session_id,
                "langfuse_tags": [agent.name]
            }
        }

    turn = 0
    while turn < max_turns:
        if stop_event and stop_event.is_set():
            logger.info(f"Agent [{agent.name}] received stop signal")
            return

        turn += 1
        logger.info(f"Agent [{agent.name}] turn {turn}/{max_turns}")

        # 1. Stream LLM response
        full_response = None
        async for chunk in model.astream([system_message] + messages, config=run_config):
            if full_response is None:
                full_response = chunk
            else:
                full_response = full_response + chunk

            # Check for thinking process (reasoning_content)
            if hasattr(chunk, "additional_kwargs") and "reasoning_content" in chunk.additional_kwargs:
                yield {"type": "thought_delta", "content": chunk.additional_kwargs["reasoning_content"]}

            if stop_event and stop_event.is_set():
                logger.info(f"Agent [{agent.name}] received stop signal during LLM streaming")
                # Persist what we have so far
                if full_response:
                    messages.append(full_response)
                    yield {"type": "message_persist", "agent": _persist_key, "message": full_response}
                return

            if chunk.content:
                yield {"type": "text_delta", "content": chunk.content}

        if full_response is None:
            yield {"type": "error", "message": "LLM returned empty response"}
            return

        messages.append(full_response)
        yield {"type": "message_persist", "agent": _persist_key, "message": full_response}

        # 2. End loop if no tool calls
        if not full_response.tool_calls:
            yield {"type": "final"}
            return

        yield {"type": "step_done"}

        # 3. Execute tool calls
        for tool_call in full_response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]

            if tool_name in sub_agent_map:
                # ── Sub-agent invocation ──
                sub_agent = sub_agent_map[tool_name]
                task = tool_args.get("task", "")
                logger.info(f"Agent [{agent.name}] delegating to sub-agent [{sub_agent.name}]: {task}")

                yield {"type": "sub_agent_start", "name": sub_agent.name, "task": task}

                sub_persist_key = f"{sub_agent.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

                # Run sub-agent loop with its own context
                sub_messages = [HumanMessage(content=task)]
                yield {"type": "message_persist", "agent": sub_persist_key, "message": sub_messages[0]}
                
                async for event in run_agent_stream(sub_agent, sub_messages, max_turns, persist_key=sub_persist_key, session_id=session_id, stop_event=stop_event):
                    yield event

                # Extract sub-agent result
                last_ai = next(
                    (m for m in reversed(sub_messages) if isinstance(m, AIMessage)),
                    None,
                )
                result_content = last_ai.content if last_ai else "Sub-agent returned no result"

                tool_message = ToolMessage(
                    content=result_content,
                    name=tool_name,
                    tool_call_id=tool_id,
                )
                messages.append(tool_message)
                yield {
                    "type": "message_persist",
                    "agent": _persist_key,
                    "message": tool_message,
                    "extra": {"sub_agent_file": sub_persist_key},
                }

                yield {"type": "sub_agent_end", "name": sub_agent.name, "result": result_content}

            else:
                # ── Regular tool execution ──
                yield {"type": "tool_start", "name": tool_name, "args": tool_args}

                tool_fn = next((t for t in agent.tools if t.name == tool_name), None)
                if tool_fn is None:
                    result_content = f"Error: Tool '{tool_name}' not found"
                else:
                    try:
                        result = await tool_fn.ainvoke(tool_args, config=run_config)
                        result_content = str(result)
                    except Exception as e:
                        logger.error(f"Tool execution error: {tool_name}", exc_info=True)
                        result_content = f"Error executing tool '{tool_name}': {str(e)}"

                tool_message = ToolMessage(
                    content=result_content,
                    name=tool_name,
                    tool_call_id=tool_id,
                )
                messages.append(tool_message)
                yield {"type": "message_persist", "agent": _persist_key, "message": tool_message}

                yield {"type": "tool_end", "name": tool_name, "result": result_content}

        yield {"type": "step_done"}

    yield {"type": "error", "message": f"Agent [{agent.name}] exceeded max turns: {max_turns}"}
