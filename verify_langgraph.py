import asyncio
import os
import sys

# Add current directory to path
sys.path.append(os.getcwd())

from app.core.graph import workflow, DB_PATH
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langchain_core.messages import HumanMessage

async def test_chat():
    print("--- Testing Main Agent ---")
    config = {"configurable": {"thread_id": "test_conv_1"}}
    inputs = {"messages": [HumanMessage(content="你好，你是谁？")]}
    
    async with AsyncSqliteSaver.from_conn_string(DB_PATH) as saver:
        graph = workflow.compile(checkpointer=saver)
        async for event in graph.astream_events(inputs, config=config, version="v2"):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                if content:
                    print(content, end="", flush=True)
    print("\n")

if __name__ == "__main__":
    asyncio.run(test_chat())
