import asyncio
from typing import Annotated, TypedDict, Union

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool, InjectedToolCallId
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END, add_messages
from langgraph.prebuilt import ToolNode

from app.agents.base import Agent
from app.core.llm import DEFAULT_MODEL
from app.schemas.agent import SubAgentInput


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def create_agent_subgraph(agent: Agent) -> StateGraph:
    """Dynamically compiles a StateGraph builder for a given Agent configuration."""
    def call_model(state: AgentState):
        system_msg = SystemMessage(content=agent.instructions)
        model = DEFAULT_MODEL
        if agent.tools:
            model = model.bind_tools(agent.tools)
        response = model.invoke([system_msg] + state["messages"])
        return {"messages": [response]}

    builder = StateGraph(AgentState)
    builder.add_node("agent", call_model)
    
    if agent.tools:
        builder.add_node("tools", ToolNode(agent.tools))
        
        def route(state: AgentState):
            last_message = state["messages"][-1]
            if getattr(last_message, "tool_calls", None):
                return "tools"
            return END
            
        builder.add_conditional_edges("agent", route)
        builder.add_edge("tools", "agent")
    else:
        builder.add_edge("agent", END)
        
    builder.add_edge(START, "agent")
    
    return builder


def create_agent_tool(agent: Agent) -> StructuredTool:
    """Wraps an Agent subgraph into a callable Tool for another agent."""
    builder = create_agent_subgraph(agent)
    
    async def transfer_to_agent(
        task: str, 
        context: str, 
        config: RunnableConfig, 
        tool_call_id: Annotated[str, InjectedToolCallId]
    ):
        from app.core.graph import DB_PATH
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        
        parent_thread_id = config["configurable"]["thread_id"]
        # 使用基于 tool_call_id 的确定性子线程 ID
        sub_thread_id = f"{parent_thread_id}:{tool_call_id}"
        
        sub_config = {
            "configurable": {"thread_id": sub_thread_id},
            "callbacks": config.get("callbacks", [])
        }
        
        # Combine context and task into the first human message
        combined_prompt = task
        if context:
            combined_prompt = f"前置上下文:\n{context}\n\n目标任务:\n{task}"
            
        inputs = {"messages": [HumanMessage(content=combined_prompt)]}
        
        async with AsyncSqliteSaver.from_conn_string(DB_PATH) as saver:
            graph = builder.compile(checkpointer=saver)
            final_state = await graph.ainvoke(inputs, config=sub_config)
            
        last_ai = next((m for m in reversed(final_state["messages"]) if isinstance(m, AIMessage)), None)
        result = last_ai.content if last_ai else f"{agent.name} finished with no content."
        
        return result, {"sub_thread_id": sub_thread_id}
        
    return StructuredTool.from_function(
        coroutine=transfer_to_agent,
        name=f"transfer_to_{agent.name}",
        description=f"委派任务给专门的子代理解：{agent.name}。能力范围：{agent.instructions[:200]}。当你需要深入查阅或执行该领域的事务时调用此工具。",
        args_schema=SubAgentInput,
        response_format="content_and_artifact"
    )
