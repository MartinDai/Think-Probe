import asyncio
import json

from PIL import Image
from langchain_core.messages import HumanMessage
from langgraph.constants import END
from langgraph.graph.state import CompiledStateGraph, StateGraph

from app.node import NodeType, NodeState
from app.node.node_manager import triage_node, shell_node, java_diagnosis_node
from app.utils.logger import logger


def route_command(state: NodeState) -> str:
    return state.current


async def build_graph(entry_point: str) -> CompiledStateGraph:
    workflow = StateGraph(NodeState)
    workflow.add_node("triage", triage_node)
    workflow.add_node("shell", shell_node)
    workflow.add_node("java_diagnosis", java_diagnosis_node)

    # Use conditional edges to dynamically route based on the 'goto' value
    workflow.add_conditional_edges(
        "triage",
        route_command,
        {
            "shell": "shell",
            "java_diagnosis": "java_diagnosis",
            END: END,
        }
    )
    workflow.add_conditional_edges(
        "shell",
        route_command,
        {
            "triage": "triage",
            END: END,
        }
    )
    workflow.add_conditional_edges(
        "java_diagnosis",
        route_command,
        {
            "triage": "triage",
            END: END,
        }
    )

    workflow.set_entry_point(entry_point)

    return workflow.compile()


async def run_workflow(graph: CompiledStateGraph, user_input: str):
    logger.info(f"Starting workflow with input: {user_input}")
    initial_state = NodeState(messages=[HumanMessage(content=user_input)], current=NodeType.TRIAGE.value,
                              remaining_steps=10)
    try:
        result = await graph.ainvoke(initial_state)
        last_message = result["messages"][-1]
        logger.info(f"Final Messages: {json.dumps(result["messages"], default=str, ensure_ascii=False, indent=2)}")
        return last_message.content
    except Exception as e:
        logger.error(f"Error in workflow: {str(e)}")
        return f"Error: {str(e)}"


def show_graph(state_graph: CompiledStateGraph):
    try:
        img_data = state_graph.get_graph().draw_mermaid_png()
        with open('graph.png', 'wb') as f:
            f.write(img_data)
        img = Image.open('graph.png')
        img.show()
        logger.info("Graph visualization generated and displayed")
    except Exception as e:
        logger.error(f"Failed to generate graph visualization: {str(e)}")


async def main():
    graph = await build_graph(NodeType.TRIAGE.value)
    # show_graph(graph)
    result = await run_workflow(graph, "调用工具看看我本地电脑/Users/martin/Downloads目录下有哪些文件")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
