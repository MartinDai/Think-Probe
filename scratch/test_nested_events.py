import asyncio
from typing import Annotated, TypedDict
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.tools import StructuredTool
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END, add_messages
from langchain_openai import ChatOpenAI
import os

# Set dummy API key for testing events logic (won't actually call if we mock or just check structure)
os.environ["OPENAI_API_KEY"] = "sk-..."

class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

async def call_sub_graph(task: str, config: RunnableConfig):
    # This simulates the transfer_to_java_expert logic
    sub_builder = StateGraph(State)
    model = ChatOpenAI(model="gpt-3.5-turbo") # Or any model
    
    async def sub_node(state: State):
        # In a real run, this would stream if called via astream
        # But here we call it via invoke/ainvoke
        return {"messages": [AIMessage(content="Sub Result")]}
    
    sub_builder.add_node("sub_node", sub_node)
    sub_builder.add_edge(START, "sub_node")
    sub_builder.add_edge("sub_node", END)
    sub_graph = sub_builder.compile()
    
    # Passing the parent's callbacks
    sub_config = {"configurable": {"thread_id": "sub"}, "callbacks": config.get("callbacks", [])}
    
    # Current project uses ainvoke
    res = await sub_graph.ainvoke({"messages": [HumanMessage(content=task)]}, config=sub_config)
    return {"content": res["messages"][-1].content}

delegate_tool = StructuredTool.from_function(
    coroutine=call_sub_graph,
    name="delegate",
    description="Delegate to sub graph"
)

async def main_node(state: State, config: RunnableConfig):
    # Simulate a tool call
    return {"messages": [AIMessage(content="", tool_calls=[{"name": "delegate", "args": {"task": "test"}, "id": "1"}])]}

async def tool_node(state: State, config: RunnableConfig):
    res = await delegate_tool.ainvoke(state["messages"][-1].tool_calls[0]["args"], config=config)
    return {"messages": [AIMessage(content=res["content"])]}

builder = StateGraph(State)
builder.add_node("main", main_node)
builder.add_node("tools", tool_node)
builder.add_edge(START, "main")
builder.add_edge("main", "tools")
builder.add_edge("tools", END)
graph = builder.compile()

async def main():
    print("Testing astream_events with nested ainvoke...")
    async for event in graph.astream_events({"messages": [HumanMessage(content="start")]}, version="v2"):
        kind = event["event"]
        name = event.get("name")
        print(f"Event: {kind}, Name: {name}")

if __name__ == "__main__":
    asyncio.run(main())
