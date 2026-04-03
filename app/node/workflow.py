import asyncio
from datetime import datetime

from langchain_core.messages import BaseMessage, AIMessage, ToolMessage, SystemMessage, HumanMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.node import Agent
from app.model import DEFAULT_MODEL
from app.utils.logger import logger
from app.config.env_config import get_env_variable
import os

langfuse_secret = get_env_variable("LANGFUSE_SECRET_KEY")
langfuse_public = get_env_variable("LANGFUSE_PUBLIC_KEY")
langfuse_host = get_env_variable("LANGFUSE_BASE_URL") or get_env_variable("LANGFUSE_HOST")
if langfuse_host and "LANGFUSE_HOST" not in os.environ:
    os.environ["LANGFUSE_HOST"] = langfuse_host




class MaxTurnsExceeded(Exception):
    pass


class SubAgentInput(BaseModel):
    """Input schema for sub-agent delegation tools"""
    task: str = Field(description="A clear description of the task to delegate to the sub-agent")


def _create_sub_agent_tool(sub_agent: Agent) -> StructuredTool:
    """
    Create a tool definition that represents delegating a task to a sub-agent.

    The tool function itself is a placeholder — actual sub-agent execution
    is handled in the agent loop when this tool is called.
    """

    def _placeholder(task: str) -> str:
        return ""

    return StructuredTool(
        name=f"transfer_to_{sub_agent.name}",
        description=(
            f"Delegate a task to the '{sub_agent.name}' sub-agent. "
            f"You must provide a clear and complete task description. "
            f"Sub-agent capability: {sub_agent.instructions[:200]}"
        ),
        func=_placeholder,
        args_schema=SubAgentInput,
    )


async def run_agent_stream(agent: Agent, messages: list[BaseMessage], max_turns: int = 10, persist_key: str = None, session_id: str = None):
    """
    Core agent loop - OpenAI Agents SDK (OpenClaw) style.

    The loop:
        1. Call LLM (with tools + sub-agent tools bound)
        2. If response has tool_calls:
           - If it's a sub-agent call → run sub-agent loop recursively, return result
           - If it's a regular tool → execute tool
           - Continue loop
        3. If response has no tool_calls → final output → end loop

    Yields structured events:
        - {"type": "text_delta", "content": "..."}
        - {"type": "tool_start", "name": "...", "args": {...}}
        - {"type": "tool_end", "name": "...", "result": "..."}
        - {"type": "sub_agent_start", "name": "...", "task": "..."}
        - {"type": "sub_agent_end", "name": "...", "result": "..."}
        - {"type": "message_persist", "agent": "...", "message": BaseMessage}
        - {"type": "step_done"}
        - {"type": "final"}
        - {"type": "error", "message": "..."}
    """
    # persist_key determines which JSONL file to write to
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
        from langfuse.langchain import CallbackHandler
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
        turn += 1
        logger.info(f"Agent [{agent.name}] turn {turn}/{max_turns}")

        # 1. Stream LLM response
        full_response = None
        async for chunk in model.astream([system_message] + messages, config=run_config):
            if full_response is None:
                full_response = chunk
            else:
                full_response = full_response + chunk

            # Check for reasoning_content (thinking process)
            if hasattr(chunk, "additional_kwargs") and "reasoning_content" in chunk.additional_kwargs:
                yield {"type": "thought_delta", "content": chunk.additional_kwargs["reasoning_content"]}

            if chunk.content:
                yield {"type": "text_delta", "content": chunk.content}

        if full_response is None:
            yield {"type": "error", "message": "LLM returned empty response"}
            return

        messages.append(full_response)
        yield {"type": "message_persist", "agent": _persist_key, "message": full_response}

        # 2. No tool calls → final output, end loop
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

                # Each sub-agent invocation gets a unique file: {name}_{timestamp}.jsonl
                sub_persist_key = f"{sub_agent.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

                # Run sub-agent loop with its own message context
                sub_messages = [HumanMessage(content=task)]
                # Persist sub-agent's input message
                yield {"type": "message_persist", "agent": sub_persist_key, "message": sub_messages[0]}
                async for event in run_agent_stream(sub_agent, sub_messages, max_turns, persist_key=sub_persist_key, session_id=session_id):
                    yield event  # Forward sub-agent events to caller

                # Extract the sub-agent's final response
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


async def main():
    """Quick test of the agent loop with sub-agents"""
    # Define a sub-agent
    sub = Agent(
        name="greeter",
        instructions="You are a greeter. Respond with a warm greeting to the task given.",
        tools=[],
    )

    # Define main agent with sub-agent
    main_agent = Agent(
        name="main",
        instructions=(
            "You are a helpful assistant. "
            "If the user wants a greeting, delegate to the greeter sub-agent."
        ),
        tools=[],
        sub_agents=[sub],
    )

    messages = [HumanMessage(content="请打个招呼")]

    async for event in run_agent_stream(main_agent, messages):
        if event["type"] == "text_delta":
            print(event["content"], end="", flush=True)
        elif event["type"] == "sub_agent_start":
            print(f"\n>>> Delegating to [{event['name']}]: {event['task']}")
        elif event["type"] == "sub_agent_end":
            print(f"\n<<< [{event['name']}] returned: {event['result'][:100]}")
        elif event["type"] == "final":
            print("\n--- Done ---")
        elif event["type"] == "step_done":
            print()
        else:
            print(f"\n[Event] {event}")


if __name__ == "__main__":
    asyncio.run(main())
