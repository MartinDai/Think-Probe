from pathlib import Path
import asyncio
from typing import Annotated, TypedDict, Union, List, Any

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool, InjectedToolCallId
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END, add_messages
from langgraph.prebuilt import ToolNode

from app.core.llm import DEFAULT_MODEL
from app.schemas.agent import SubAgentInput


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def create_agent_subgraph(instructions: str, tools: List[Any] = None) -> StateGraph:
    """Dynamically compiles a StateGraph builder for given instructions and tools."""
    def call_model(state: AgentState):
        system_msg = SystemMessage(content=instructions)
        model = DEFAULT_MODEL
        if tools:
            model = model.bind_tools(tools)
        response = model.invoke([system_msg] + state["messages"])
        return {"messages": [response]}

    builder = StateGraph(AgentState)
    builder.add_node("agent", call_model)
    
    if tools:
        builder.add_node("tools", ToolNode(tools))
        
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


def create_sub_task_tool(all_tools: List[Any]) -> StructuredTool:
    """Creates a generic sub_task tool that uses a standard sub_agent.md prompt."""
    
    # 获取 sub_agent.md 的路径
    prompt_path = Path(__file__).parent.parent / "agents" / "prompts" / "sub_agent.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Sub-agent prompt template not found at {prompt_path}")
    
    instructions = prompt_path.read_text(encoding="utf-8")
    # 子代理默认获得传入的所有基础工具
    builder = create_agent_subgraph(instructions, all_tools)
    
    async def sub_task_executor(
        task: str, 
        context: str, 
        config: RunnableConfig, 
        tool_call_id: Annotated[str, InjectedToolCallId]
    ):
        
        parent_thread_id = config["configurable"]["thread_id"]
        # 使用基于 tool_call_id 的确定性子线程 ID
        sub_thread_id = f"{parent_thread_id}:{tool_call_id}"
        
        sub_config = {
            "configurable": {"thread_id": sub_thread_id},
            "callbacks": config.get("callbacks", [])
        }
        
        # 将背景和任务合并
        combined_prompt = task
        if context:
            combined_prompt = f"前置上下文:\n{context}\n\n目标任务:\n{task}"
            
        inputs = {"messages": [HumanMessage(content=combined_prompt)]}
        
        graph = builder.compile()
        final_state = await graph.ainvoke(inputs, config=sub_config)
            
        last_ai = next((m for m in reversed(final_state["messages"]) if isinstance(m, AIMessage)), None)
        result = last_ai.content if last_ai else "Sub-agent finished with no response content."
        
        return result, {"sub_thread_id": sub_thread_id}
        
    return StructuredTool.from_function(
        coroutine=sub_task_executor,
        name="sub_task",
        description=(
            "委派一个复杂的子任务。子代理拥有与主代理相同的工具权限，专注于独立分析、代码编写或 Bug 排错。"
            "当你需要深度排查或执行涉及多步操作的专业事务时调用此工具。"
            "任务完成后，子代理会汇报关键总结。"
        ),
        args_schema=SubAgentInput,
        response_format="content_and_artifact"
    )
