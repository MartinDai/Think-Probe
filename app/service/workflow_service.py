import logging

from langchain_core.messages import HumanMessage
from langfuse import get_client
from langfuse.langchain import CallbackHandler

from app.context.conversation_context import ConversationContext
from app.core.llm import MODEL_NAME
from app.core.graph import workflow, DB_PATH
from app.service import conversation_service
from app.utils.response_util import SSEBuilder
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
        if not await conversation_service.conversation_exists(conversation_id):
            title = message[:30] + ("..." if len(message) > 30 else "")
            await conversation_service.update_metadata(conversation_id, {"title": title})

        # Dual write: Save human user input
        await conversation_service.save_message(
            conversation_id=conversation_id,
            role="human",
            content=message
        )

        async with AsyncSqliteSaver.from_conn_string(DB_PATH) as saver:
            graph = workflow.compile(checkpointer=saver)
            
            current_sub_agent = None
            current_sub_thread_id = None
            pending_tool_calls = {} # name -> list[id]
            running_tool_calls = {} # run_id -> id
            
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
                         pass

                    if not content and not reasoning:
                        continue
                    
                    if reasoning:
                        yield SSEBuilder.reasoning(reasoning, sub_agent=current_sub_agent)
                    if content:
                        yield SSEBuilder.content(content, sub_agent=current_sub_agent)

                elif kind == "on_chat_model_end":
                    msg = event["data"].get("output")
                    if msg and hasattr(msg, "content"):
                        content = msg.content
                        tool_calls = msg.tool_calls if hasattr(msg, "tool_calls") else None
                        kwargs = msg.additional_kwargs if hasattr(msg, "additional_kwargs") else {}
                        reasoning_content = kwargs.get("reasoning_content")
                        
                        if tool_calls:
                            for tc in tool_calls:
                                name = tc['name']
                                if name not in pending_tool_calls:
                                    pending_tool_calls[name] = []
                                pending_tool_calls[name].append(tc['id'])
                        
                        # Dual Write logic
                        if current_sub_agent:
                            # 实时落库子代理的消息
                            await conversation_service.save_message(
                                conversation_id, "ai", content, tool_calls, 
                                reasoning_content=reasoning_content,
                                sub_thread_id=current_sub_thread_id
                            )
                        else:
                            # 主代理的消息，直接入库
                            await conversation_service.save_message(
                                conversation_id, "ai", content, tool_calls, reasoning_content=reasoning_content
                            )

                elif kind == "on_tool_start":
                    tool_name = event["name"]
                    tool_args = event["data"].get("input", {})
                    
                    # 为当前工具提取或生成唯一的 tool_call_id
                    tool_ids = pending_tool_calls.get(tool_name, [])
                    actual_tool_id = tool_ids.pop(0) if tool_ids else event.get("run_id")
                    running_tool_calls[event.get("run_id")] = actual_tool_id

                    if tool_name.startswith("transfer_to_"):
                        agent_name = tool_name.replace("transfer_to_", "")
                        current_sub_agent = agent_name
                        current_sub_thread_id = f"{conversation_id}:{agent_name}:{actual_tool_id}"
                        
                        # 发送子代理开始信号
                        yield SSEBuilder.sub_agent_start(
                            name=agent_name, 
                            task=tool_args.get("task", "")
                        )
                    else:
                        # 普通工具开始
                        yield SSEBuilder.tool_start(
                            name=tool_name, 
                            args=tool_args, 
                            sub_agent=current_sub_agent
                        )

                elif kind == "on_tool_end":
                    tool_name = event["name"]
                    tool_result = event["data"].get("output")
                    
                    # 尝试从结构化结果中提取主体内容
                    display_content = tool_result
                    sub_t_id = None
                    if isinstance(tool_result, dict):
                        display_content = tool_result.get("content", tool_result)
                        sub_t_id = tool_result.get("sub_thread_id")
                    elif hasattr(tool_result, "content"):
                        display_content = tool_result.content
                        if hasattr(tool_result, "artifact") and isinstance(tool_result.artifact, dict):
                            sub_t_id = tool_result.artifact.get("sub_thread_id")
                    
                    actual_tool_call_id = running_tool_calls.pop(event.get("run_id"), event.get("run_id"))
                    
                    if tool_name.startswith("transfer_to_"):
                        # 对于子代理大工具，把结果存入主线程 (ToolMessage)
                        # 注意：子代理内部产生的消息已经在产生时实时落库了
                        await conversation_service.save_message(
                            conversation_id, "tool", str(display_content),
                            tool_name=tool_name, tool_call_id=actual_tool_call_id, sub_thread_id=current_sub_thread_id
                        )
                        
                        current_sub_agent = None 
                        current_sub_thread_id = None
                        # 子代理执行结束
                        yield SSEBuilder.sub_agent_end(
                            result=str(display_content)
                        )
                    else:
                        # Dual write for common tools
                        if current_sub_agent:
                            # 子代理调用的工具，实时落库
                            await conversation_service.save_message(
                                conversation_id, "tool", str(display_content),
                                tool_name=tool_name, 
                                tool_call_id=actual_tool_call_id,
                                sub_thread_id=current_sub_thread_id
                            )
                        else:
                            # 主代理调用的工具，直接落库
                            await conversation_service.save_message(
                                conversation_id, "tool", str(display_content),
                                tool_name=tool_name, tool_call_id=actual_tool_call_id
                            )
                        
                        # 普通工具结束
                        yield SSEBuilder.tool_end(
                            name=tool_name, 
                            result=str(display_content), 
                            sub_agent=current_sub_agent
                        )

                # --- Step Done Marker ---
                elif kind == "on_chain_end":
                    pass

        # 无需手动清理锚点消息，timeline 逻辑会自动通过 AIMessage 的 tool_calls 进行关联恢复

        # Final signal
        yield SSEBuilder.step_done()

    except Exception as e:
        error_msg = f"错误: {str(e)}"
        logging.error(error_msg, exc_info=True)
        
        # 无需手动清理锚点消息

        yield SSEBuilder.error(error_msg)
    finally:
        from app.service import stop_service
        stop_service.clear_stop_event(conversation_id)
