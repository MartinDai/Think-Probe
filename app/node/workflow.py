import asyncio

from langchain_core.messages import BaseMessage, AIMessage, ToolMessage, SystemMessage, HumanMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.node import Agent
from app.model import DEFAULT_MODEL
from app.utils.logger import logger


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


async def run_agent_stream(agent: Agent, messages: list[BaseMessage], max_turns: int = 10):
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
        - {"type": "step_done"}
        - {"type": "final"}
        - {"type": "error", "message": "..."}
    """
    system_message = SystemMessage(content=agent.instructions)

    # Build sub-agent map and tools
    sub_agent_map = {f"transfer_to_{sa.name}": sa for sa in agent.sub_agents}
    sub_agent_tools = [_create_sub_agent_tool(sa) for sa in agent.sub_agents]

    # Combine regular tools + sub-agent delegation tools
    all_tools = agent.tools + sub_agent_tools

    model = DEFAULT_MODEL
    if all_tools:
        model = model.bind_tools(all_tools)

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

                # Run sub-agent loop with its own message context
                sub_messages = [HumanMessage(content=task)]
                async for event in run_agent_stream(sub_agent, sub_messages, max_turns):
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

                yield {"type": "sub_agent_end", "name": sub_agent.name, "result": result_content}

            else:
                # ── Regular tool execution ──
                yield {"type": "tool_start", "name": tool_name, "args": tool_args}

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
