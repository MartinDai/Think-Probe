from pathlib import Path
from typing import Annotated, TypedDict
import os
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END, add_messages
from langgraph.prebuilt import ToolNode

from app.agents.main import main_agent
from app.agents.java_expert import java_expert_agent
from app.core.llm import DEFAULT_MODEL
from app.core.agent_factory import create_agent_tool
from app.tools.terminal import WORKSPACE_BASE

# --- State Definition ---
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

# Persistence Setup
DB_DIR = "conversations"
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "checkpoints.db")

# --- Agent Registration ---
# Dynamically generate tools for all registered sub-agents
registered_sub_agents = [java_expert_agent]
transfer_tools = [create_agent_tool(agent) for agent in registered_sub_agents]

# Combined tools for the main agent (transfer tools + native tools like terminal)
all_main_tools = transfer_tools + main_agent.tools

# --- Main Graph ---
def call_main_model(state: AgentState, config: RunnableConfig):
    # 1. 尝试从动态 workspace 读取任务进度
    thread_id = config.get("configurable", {}).get("thread_id", "unknown")
    workspace_dir = WORKSPACE_BASE / thread_id
    task_content = ""
    task_file = workspace_dir / "task.md"
    
    if task_file.exists():
        try:
            with open(task_file, "r") as f:
                task_content = f.read().strip()
        except Exception:
            pass

    # 2. 构建动态指令
    instructions = main_agent.instructions
    if task_content:
        instructions += f"\n\n### 当前任务进度 (Source of Truth):\n```markdown\n{task_content}\n```\n请基于上述进度继续执行，不要重复已完成的步骤。"

    system_msg = SystemMessage(content=instructions)
    
    # 3. 过滤掉历史消息中的所有旧 SystemMessage，确保只有一个最新的指令
    filtered_messages = [m for m in state["messages"] if not isinstance(m, SystemMessage)]
    
    # bind all dynamic sub-agent-tools and native tools to the main model
    model = DEFAULT_MODEL
    if all_main_tools:
        model = model.bind_tools(all_main_tools)
        
    response = model.invoke([system_msg] + filtered_messages)
    return {"messages": [response]}


def route_main(state: AgentState):
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return END

main_builder = StateGraph(AgentState)
main_builder.add_node("main", call_main_model)

if all_main_tools:
    # Use native LangGraph ToolNode with all available tools
    main_builder.add_node("tools", ToolNode(all_main_tools))
    main_builder.add_conditional_edges("main", route_main)
    main_builder.add_edge("tools", "main")
else:
    main_builder.add_edge("main", END)

main_builder.add_edge(START, "main")

# Export only the workflow builder; it will be compiled with a checkpointer where used.
workflow = main_builder
