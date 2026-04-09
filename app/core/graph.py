import os
import asyncio
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END, add_messages
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import ToolNode

from app.agents.main import main_agent
from app.agents.java_expert import java_expert_agent
from app.core.llm import DEFAULT_MODEL
from app.schemas.agent import SubAgentInput

# --- State Definition ---
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

# Persistence Setup
DB_DIR = "conversations"
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "checkpoints.db")

# --- Java Expert Sub-Graph ---

def call_expert_model(state: AgentState):
    system_msg = SystemMessage(content=java_expert_agent.instructions)
    model = DEFAULT_MODEL.bind_tools(java_expert_agent.tools)
    response = model.invoke([system_msg] + state["messages"])
    return {"messages": [response]}

expert_builder = StateGraph(AgentState)
expert_builder.add_node("expert", call_expert_model)
expert_builder.add_node("tools", ToolNode(java_expert_agent.tools))
expert_builder.add_edge(START, "expert")

def route_expert(state: AgentState):
    last_message = state["messages"][-1]
    if not last_message.tool_calls:
        return END
    return "tools"

expert_builder.add_conditional_edges("expert", route_expert)
expert_builder.add_edge("tools", "expert")
# expert_builder will be compiled inside the tool

# --- Tool for Delegation ---

# --- Tool for Delegation ---

async def transfer_to_java_expert(task: str, config: RunnableConfig):
    """
    Delegates task to the java_expert sub-graph.
    This function will be called as a tool by the main agent.
    """
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    
    # Create a unique thread ID for this sub-execution to keep context separate but linked
    parent_thread_id = config["configurable"]["thread_id"]
    sub_thread_id = f"{parent_thread_id}:java_expert:{asyncio.get_event_loop().time()}"
    
    sub_config = {
        "configurable": {"thread_id": sub_thread_id},
        "callbacks": config.get("callbacks", [])
    }
    
    # Run the sub-graph
    inputs = {"messages": [HumanMessage(content=task)]}
    
    # Open a new checkpointer for the sub-graph
    async with AsyncSqliteSaver.from_conn_string(DB_PATH) as saver:
        graph = expert_builder.compile(checkpointer=saver)
        # Wait for completion
        final_state = await graph.ainvoke(inputs, config=sub_config)
    
    # Get the last AI message as the result
    last_ai = next((m for m in reversed(final_state["messages"]) if isinstance(m, AIMessage)), None)
    result = last_ai.content if last_ai else "Expert finished with no content."
    
    return {
        "content": result,
        "sub_thread_id": sub_thread_id
    }

java_expert_tool = StructuredTool.from_function(
    coroutine=transfer_to_java_expert,
    name="transfer_to_java_expert",
    description=f"委派任务给 java_expert。能力范围：{java_expert_agent.instructions[:200]}",
    args_schema=SubAgentInput,
)

# --- Main Graph ---

def call_main_model(state: AgentState):
    system_msg = SystemMessage(content=main_agent.instructions)
    model = DEFAULT_MODEL.bind_tools([java_expert_tool])
    response = model.invoke([system_msg] + state["messages"])
    return {"messages": [response]}

# --- Graph Construction ---

def route_main(state: AgentState):
    last_message = state["messages"][-1]
    if not last_message.tool_calls:
        return END
    return "tools"

main_builder = StateGraph(AgentState)
main_builder.add_node("main", call_main_model)

async def custom_tool_executor(state: AgentState, config: RunnableConfig):
    last_message = state["messages"][-1]
    tool_calls = last_message.tool_calls
    results = []
    for tc in tool_calls:
        if tc["name"] == "transfer_to_java_expert":
            # Using tool.ainvoke ensures on_tool_start events are emitted
            res = await java_expert_tool.ainvoke(tc["args"], config=config)
            results.append(ToolMessage(
                tool_call_id=tc["id"],
                name="transfer_to_java_expert",
                content=res["content"],
                additional_kwargs={"sub_thread_id": res["sub_thread_id"]}
            ))
    return {"messages": results}

main_builder.add_node("tools", custom_tool_executor)
main_builder.add_edge(START, "main")
main_builder.add_conditional_edges("main", route_main)
main_builder.add_edge("tools", "main")

# Export only the workflow builder; it will be compiled with a checkpointer where used.
workflow = main_builder
