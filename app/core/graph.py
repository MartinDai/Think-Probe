import os
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph import StateGraph, START, END, add_messages
from langgraph.prebuilt import ToolNode

from app.agents.main import main_agent
from app.agents.java_expert import java_expert_agent
from app.core.llm import DEFAULT_MODEL
from app.core.agent_factory import create_agent_tool

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
agent_tools = [create_agent_tool(agent) for agent in registered_sub_agents]


# --- Main Graph ---
def call_main_model(state: AgentState):
    system_msg = SystemMessage(content=main_agent.instructions)
    
    # bind all dynamic sub-agent-tools to the main model
    model = DEFAULT_MODEL
    if agent_tools:
        model = model.bind_tools(agent_tools)
        
    response = model.invoke([system_msg] + state["messages"])
    return {"messages": [response]}


def route_main(state: AgentState):
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return END

main_builder = StateGraph(AgentState)
main_builder.add_node("main", call_main_model)

if agent_tools:
    # Use native LangGraph ToolNode instead of cumbersome manual execution
    main_builder.add_node("tools", ToolNode(agent_tools))
    main_builder.add_conditional_edges("main", route_main)
    main_builder.add_edge("tools", "main")
else:
    main_builder.add_edge("main", END)

main_builder.add_edge(START, "main")

# Export only the workflow builder; it will be compiled with a checkpointer where used.
workflow = main_builder
