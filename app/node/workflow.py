import asyncio
import json

from langchain_core.messages import BaseMessage, AIMessage, ToolMessage, SystemMessage, HumanMessage

from app.node import Agent
from app.model import DEFAULT_MODEL
from app.utils.logger import logger


class MaxTurnsExceeded(Exception):
    pass


async def run_agent_stream(agent: Agent, messages: list[BaseMessage], max_turns: int = 10):
    """
    Core agent loop - OpenAI Agents SDK (OpenClaw) style.

    The loop:
        1. Call LLM (with tools bound)
        2. If response has tool_calls → execute tools → continue loop
        3. If response has no tool_calls → final output → end loop

    Yields structured events for the caller to handle streaming:
        - {"type": "text_delta", "content": "..."}   — streaming text chunk
        - {"type": "tool_start", "name": "...", "args": {...}}  — tool execution starting
        - {"type": "tool_end", "name": "...", "result": "..."}  — tool execution finished
        - {"type": "step_done"}  — a reasoning/tool step completed
        - {"type": "final"}     — agent finished, final output delivered
        - {"type": "error", "message": "..."}  — error occurred
    """
    system_message = SystemMessage(content=agent.instructions)

    model = DEFAULT_MODEL
    if agent.tools:
        model = model.bind_tools(agent.tools)

    turn = 0
    while turn < max_turns:
        turn += 1
        logger.info(f"Agent [{agent.name}] turn {turn}/{max_turns}")

        # 1. Stream LLM response
        full_response = None
        async for chunk in model.astream([system_message] + messages):
            if full_response is None:
                full_response = chunk
            else:
                full_response = full_response + chunk

            # Yield text content for real-time streaming
            if chunk.content:
                yield {"type": "text_delta", "content": chunk.content}

        if full_response is None:
            yield {"type": "error", "message": "LLM returned empty response"}
            return

        messages.append(full_response)

        # 2. No tool calls → final output, end loop
        if not full_response.tool_calls:
            yield {"type": "final"}
            return

        # Signal that this LLM thinking step is done (before tool execution)
        yield {"type": "step_done"}

        # 3. Execute tool calls
        for tool_call in full_response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]

            yield {"type": "tool_start", "name": tool_name, "args": tool_args}

            # Find the matching tool
            tool_fn = next((t for t in agent.tools if t.name == tool_name), None)
            if tool_fn is None:
                result_content = f"Error: Tool '{tool_name}' not found"
            else:
                try:
                    result = await tool_fn.ainvoke(tool_args)
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

            yield {"type": "tool_end", "name": tool_name, "result": result_content}

        # After all tools executed, signal step done before next LLM call
        yield {"type": "step_done"}

    # Exceeded max turns
    yield {"type": "error", "message": f"Agent [{agent.name}] exceeded max turns: {max_turns}"}


async def main():
    """Quick test of the agent loop"""
    agent = Agent(
        name="test",
        instructions="You are a helpful assistant.",
        tools=[],
    )
    messages = [HumanMessage(content="Hello, who are you?")]

    async for event in run_agent_stream(agent, messages):
        if event["type"] == "text_delta":
            print(event["content"], end="", flush=True)
        elif event["type"] == "final":
            print("\n--- Done ---")
        else:
            print(f"\n[Event] {event}")


if __name__ == "__main__":
    asyncio.run(main())
