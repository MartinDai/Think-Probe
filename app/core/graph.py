from typing import Annotated, TypedDict, Any

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END, add_messages
from langgraph.prebuilt import ToolNode

from app.agents.main import main_agent, get_main_agent_instructions
from app.core.agent_factory import create_sub_task_tool
from app.core.llm import DEFAULT_MODEL, invoke_with_retry
from app.service.context_compaction_service import build_compaction_prompt
from app.tools.terminal import get_workspace_dir


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def build_workflow(runtime_tools: list[Any] | None = None) -> StateGraph:
    runtime_tools = runtime_tools or []
    base_tools = list(main_agent.tools) + list(runtime_tools)
    sub_task_tool = create_sub_task_tool(base_tools)
    all_main_tools = [sub_task_tool] + base_tools
    mcp_tool_names = [getattr(tool, "name", "") for tool in runtime_tools]

    def call_main_model(state: AgentState, config: RunnableConfig):
        thread_id = config.get("configurable", {}).get("thread_id", "default_session")
        workspace_dir = get_workspace_dir(thread_id)

        instructions = get_main_agent_instructions(mcp_tool_names=mcp_tool_names)
        instructions += build_compaction_prompt(thread_id)

        task_file = workspace_dir / "task.md"
        if task_file.exists():
            try:
                task_content = task_file.read_text(encoding="utf-8").strip()
                if task_content:
                    instructions += (
                        "\n\n---\n"
                        "# Current Task Progress\n"
                        f"```markdown\n{task_content}\n```\n"
                        "请基于上述进度继续执行，从第一个未完成的步骤开始。"
                    )
            except Exception:
                pass

        system_msg = SystemMessage(content=instructions)
        model = DEFAULT_MODEL
        if all_main_tools:
            model = model.bind_tools(all_main_tools)

        response = invoke_with_retry(model, [system_msg] + state["messages"])
        return {"messages": [response]}

    def route_main(state: AgentState):
        last_message = state["messages"][-1]
        if getattr(last_message, "tool_calls", None):
            return "tools"
        return END

    main_builder = StateGraph(AgentState)
    main_builder.add_node("main", call_main_model)

    if all_main_tools:
        main_builder.add_node("tools", ToolNode(all_main_tools))
        main_builder.add_conditional_edges("main", route_main)
        main_builder.add_edge("tools", "main")
    else:
        main_builder.add_edge("main", END)

    main_builder.add_edge(START, "main")
    return main_builder
