from pathlib import Path
from typing import Annotated, TypedDict
import os
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END, add_messages
from langgraph.prebuilt import ToolNode

from app.agents.main import main_agent
from app.core.llm import DEFAULT_MODEL
from app.core.agent_factory import create_sub_task_tool
from app.tools.terminal import WORKSPACE_BASE

# --- State Definition ---
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

# Persistence Setup
DB_DIR = "conversations"
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "checkpoints.db")

# --- Agent Registration ---
# 主 Agent 的基础工具集（文件、搜索、终端等）
base_tools = main_agent.tools

# 注册通用的子任务委派工具，它可以使用所有基础工具
sub_task_tool = create_sub_task_tool(base_tools)

# 主 Agent 的完整工具集 = 子任务工具 + 基础工具
all_main_tools = [sub_task_tool] + base_tools

# --- Main Graph ---
def call_main_model(state: AgentState, config: RunnableConfig):
    # 1. 读取工作空间中的任务进度（如果存在）
    thread_id = config.get("configurable", {}).get("thread_id", "unknown")
    workspace_dir = WORKSPACE_BASE / thread_id

    instructions = main_agent.instructions

    # 2. 注入任务进度上下文
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
    
    # 3. 绑定全部工具并调用
    model = DEFAULT_MODEL
    if all_main_tools:
        model = model.bind_tools(all_main_tools)
        
    response = model.invoke([system_msg] + state["messages"])
    return {"messages": [response]}


def route_main(state: AgentState):
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return END

main_builder = StateGraph(AgentState)
main_builder.add_node("main", call_main_model)

if all_main_tools:
    # 使用 LangGraph 原生 ToolNode 处理所有工具调用
    main_builder.add_node("tools", ToolNode(all_main_tools))
    main_builder.add_conditional_edges("main", route_main)
    main_builder.add_edge("tools", "main")
else:
    main_builder.add_edge("main", END)

main_builder.add_edge(START, "main")

# 导出 workflow builder，在使用处编译并注入 checkpointer
workflow = main_builder
