import asyncio
from typing import Annotated, TypedDict
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END, add_messages

class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

async def my_tool(task: str, config: RunnableConfig):
    print(f"Tool executing with task: {task}")
    return "Tool Result"

tool = StructuredTool.from_function(
    func=my_tool,
    name="my_tool",
    description="A test tool",
)

async def node_call_tool(state: State, config: RunnableConfig):
    # This is the pattern I used in graph.py
    # res = await my_tool(state["messages"][-1].content, config) # Current way
    
    # Attempting more "Standard" way:
    res = await tool.ainvoke({"task": "test task"}, config=config)
    
    return {"messages": [ToolMessage(tool_call_id="123", content=res, name="my_tool")]}

builder = StateGraph(State)
builder.add_node("node", node_call_tool)
builder.add_edge(START, "node")
builder.add_edge("node", END)
graph = builder.compile()

async def main():
    async for event in graph.astream_events({"messages": [HumanMessage(content="start")]}, version="v2"):
        print(f"Event: {event['event']}, Name: {event.get('name')}")

if __name__ == "__main__":
    asyncio.run(main())
