import json
import logging

from langchain_core.messages import HumanMessage
from langfuse import get_client
from langfuse.langchain import CallbackHandler

from app.context.conversation_context import ConversationContext
from app.core.llm import MODEL_NAME
from app.core.graph import workflow, DB_PATH
from app.service import conversation_service
from app.utils import response_util
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


async def process_message(message: str, context: ConversationContext):
    conversation_id = context.conversation_id
    
    trace_name = message[:50] if message else "Chat Interaction"
    langfuse_handler = CallbackHandler()
    
    # LangGraph config
    config = {
        "configurable": {"thread_id": conversation_id},
        "callbacks": [langfuse_handler],
        "metadata": {
            "langfuse_session_id": conversation_id,
            "langfuse_trace_name": trace_name
        }
    }
    
    from app.service import stop_service
    # Note: LangGraph doesn't have a direct 'stop_event' in astream_events easily, 
    # but we can check it between events or use a more advanced approach.
    stop_event = stop_service.get_stop_event(conversation_id)

    # Initial user message is handled by graph.astream_events inputs
    inputs = {"messages": [HumanMessage(content=message)]}

    try:
        # We update the metadata (title) for new conversations
        if not conversation_service.conversation_exists(conversation_id):
            title = message[:30] + ("..." if len(message) > 30 else "")
            conversation_service.update_metadata(conversation_id, {"title": title})

        # Use langfuse for tracing if configured
        # Note: LangGraph integrates with langfuse via callbacks if passed in config
        
        async with AsyncSqliteSaver.from_conn_string(DB_PATH) as saver:
            graph = workflow.compile(checkpointer=saver)
            
            current_sub_agent = None
            async for event in graph.astream_events(inputs, config=config, version="v2", name=trace_name):
                kind = event["event"]
                # logging.info(f"Event Trace: {kind} - {event.get('name')}")

                if stop_event and stop_event.is_set():
                    logging.info(f"Stop signal received for {conversation_id}")
                    break

                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    content = chunk.content if hasattr(chunk, "content") else ""
                    # 适配某些模型可能将思考过程放在不同字段的情况
                    reasoning = ""
                    if hasattr(chunk, "additional_kwargs") and "reasoning_content" in chunk.additional_kwargs:
                        reasoning = chunk.additional_kwargs["reasoning_content"]
                    elif hasattr(chunk, "invalid_tool_calls") and chunk.invalid_tool_calls:
                         # 某些模型可能在 streaming 时返回这个
                        pass

                    if not content and not reasoning:
                        continue
                    
                    response_chunk = response_util.create_chunk(
                        conversation_id,
                        content,
                        reasoning
                    )
                    
                    # 关键修复：标记当前流是否属于子代理
                    if current_sub_agent:
                        response_chunk["sub_agent"] = current_sub_agent

                    yield f"data: {json.dumps(response_chunk)}\n\n"

                elif kind == "on_tool_start":
                    tool_name = event["name"]
                    tool_args = event["data"].get("input", {})
                    
                    if tool_name == "transfer_to_java_expert":
                        current_sub_agent = "java_expert" # 记录当前激活的子代理
                        # 发送子代理开始信号
                        response_chunk = response_util.create_chunk(conversation_id)
                        response_chunk["choices"][0]["delta"]["sub_agent_start"] = {
                            "name": "java_expert",
                            "task": tool_args.get("task", "")
                        }
                        yield f"data: {json.dumps(response_chunk)}\n\n"
                    else:
                         # 普通工具开始
                        response_chunk = response_util.create_chunk(conversation_id)
                        response_chunk["choices"][0]["delta"]["tool_start"] = {
                            "name": tool_name,
                            "args": tool_args
                        }
                        yield f"data: {json.dumps(response_chunk)}\n\n"

                elif kind == "on_tool_end":
                    tool_name = event["name"]
                    tool_result = event["data"].get("output")
                    
                    # 尝试从结构化结果中提取主体内容
                    display_content = tool_result
                    if isinstance(tool_result, dict):
                        display_content = tool_result.get("content", tool_result)
                    elif hasattr(tool_result, "content"):
                        display_content = tool_result.content
                    
                    if tool_name == "transfer_to_java_expert":
                        current_sub_agent = None # 清除激活状态
                        # 子代理执行结束
                        response_chunk = response_util.create_chunk(conversation_id)
                        response_chunk["choices"][0]["delta"]["sub_agent_end"] = {
                            "result": str(display_content)
                        }
                        yield f"data: {json.dumps(response_chunk)}\n\n"
                    else:
                        # 普通工具结束
                        response_chunk = response_util.create_chunk(conversation_id)
                        response_chunk["choices"][0]["delta"]["tool_end"] = {
                            "name": tool_name,
                            "result": str(display_content)
                        }
                        yield f"data: {json.dumps(response_chunk)}\n\n"

                # --- Step Done Marker ---
                elif kind == "on_chain_end":
                    # We skip most on_chain_end except the top-level or node-level to send step_done
                    # But to avoid too many events, we just send a final one
                    pass

        # Final signal
        yield f"data: {json.dumps(response_util.create_step_done(conversation_id))}\n\n"

    except Exception as e:
        content = f"错误: {str(e)}"
        logging.error(content, exc_info=True)
        response_chunk = response_util.create_chunk(
            conversation_id=conversation_id,
            content=content,
            role="assistant",
            model=MODEL_NAME,
        )
        yield f"data: {json.dumps(response_chunk)}\n\n"
    finally:
        stop_service.clear_stop_event(conversation_id)
