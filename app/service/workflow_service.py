import logging

from langchain_core.messages import HumanMessage
from langfuse import get_client
from langfuse.langchain import CallbackHandler

from app.context.conversation_context import ConversationContext
from app.core.llm import MODEL_NAME
from app.core.graph import build_workflow
from app.service import context_compaction_service, conversation_service
from app.service.mcp_service import mcp_service
from app.utils.response_util import SSEBuilder


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

        # Save human user input to DB
        await conversation_service.save_message(
            conversation_id=conversation_id,
            role="human",
            content=message
        )

        # Explicitly load conversation history from DB to maintain multi-turn context (since checkpointer is removed)
        history = await conversation_service.get_messages(conversation_id)
        inputs = {
            "messages": context_compaction_service.prepare_messages_for_model(
                conversation_id,
                history,
            )
        }

        runtime_tools = await mcp_service.load_enabled_tools()
        graph = build_workflow(runtime_tools).compile()
        
        pending_tool_calls = {} # name -> list[id]
        running_tool_calls = {} # run_id -> id
        sub_task_run_threads = {} # run_id -> sub_thread_id

        def resolve_sub_thread_id(event: dict) -> str | None:
            metadata = event.get("metadata") or {}
            metadata_sub_thread_id = metadata.get("sub_thread_id")
            if metadata_sub_thread_id:
                return metadata_sub_thread_id

            direct_run_id = event.get("run_id")
            if direct_run_id in sub_task_run_threads:
                return sub_task_run_threads[direct_run_id]

            for parent_run_id in reversed(event.get("parent_ids", [])):
                if parent_run_id in sub_task_run_threads:
                    return sub_task_run_threads[parent_run_id]
            return None
        
        async for event in graph.astream_events(inputs, config=config, version="v2", name=trace_name):
            kind = event["event"]
            # logging.info(f"Event Trace: {kind} - {event.get('name')}")

            if stop_event and stop_event.is_set():
                logging.info(f"Stop signal received for {conversation_id}")
                break

            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                content = chunk.content if hasattr(chunk, "content") else ""
                event_sub_thread_id = resolve_sub_thread_id(event)
                # 适配某些模型可能将思考过程放在不同字段的情况
                reasoning = ""
                if hasattr(chunk, "additional_kwargs") and "reasoning_content" in chunk.additional_kwargs:
                    reasoning = chunk.additional_kwargs["reasoning_content"]
                elif hasattr(chunk, "invalid_tool_calls") and chunk.invalid_tool_calls:
                     pass

                if not content and not reasoning:
                    continue
                
                if reasoning:
                    yield SSEBuilder.reasoning(reasoning, sub_thread_id=event_sub_thread_id)
                if content:
                    yield SSEBuilder.content(content, sub_thread_id=event_sub_thread_id)

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
                    
                    event_sub_thread_id = resolve_sub_thread_id(event)

                    # Save AI response to DB
                    if event_sub_thread_id:
                        # 实时落库子代理的消息
                        await conversation_service.save_message(
                            conversation_id, "ai", content, tool_calls, 
                            reasoning_content=reasoning_content,
                            sub_thread_id=event_sub_thread_id
                        )
                    else:
                        # 主代理的消息，直接入库
                        await conversation_service.save_message(
                            conversation_id, "ai", content, tool_calls, reasoning_content=reasoning_content
                        )

            elif kind == "on_tool_start":
                tool_name = event["name"]
                tool_args = event["data"].get("input", {})
                parent_sub_thread_id = resolve_sub_thread_id(event)
                
                # 为当前工具提取或生成唯一的 tool_call_id
                tool_ids = pending_tool_calls.get(tool_name, [])
                actual_tool_id = tool_ids.pop(0) if tool_ids else event.get("run_id")
                running_tool_calls[event.get("run_id")] = actual_tool_id

                if tool_name == "sub_task":
                    # 直接生成子线程 ID
                    sub_thread_id = f"{conversation_id}:{actual_tool_id}"
                    sub_task_run_threads[event.get("run_id")] = sub_thread_id
                    
                    # 发送子代理开始信号
                    yield SSEBuilder.sub_agent_start(
                        task=tool_args.get("task", "") or "执行子任务",
                        sub_thread_id=sub_thread_id,
                        parent_sub_thread_id=parent_sub_thread_id
                    )
                else:
                    # 普通工具开始
                    yield SSEBuilder.tool_start(
                        name=tool_name, 
                        args=tool_args, 
                        sub_thread_id=parent_sub_thread_id
                    )

            elif kind == "on_tool_end":
                tool_name = event["name"]
                tool_result = event["data"].get("output")
                
                # 尝试从结构化结果中提取主体内容
                display_content = tool_result
                if isinstance(tool_result, dict):
                    display_content = tool_result.get("content", tool_result)
                elif hasattr(tool_result, "content"):
                    display_content = tool_result.content
                
                actual_tool_call_id = running_tool_calls.pop(event.get("run_id"), event.get("run_id"))
                
                if tool_name == "sub_task":
                    sub_thread_id = sub_task_run_threads.pop(event.get("run_id"), None)
                    # 对于子代理大工具，把结果存入主线程 (ToolMessage)
                    await conversation_service.save_message(
                        conversation_id, "tool", str(display_content),
                        tool_name=tool_name, tool_call_id=actual_tool_call_id, sub_thread_id=sub_thread_id
                    )
                    
                    # 子代理执行结束
                    yield SSEBuilder.sub_agent_end(
                        result=str(display_content),
                        sub_thread_id=sub_thread_id
                    )
                else:
                    event_sub_thread_id = resolve_sub_thread_id(event)
                    # Save common tool result to DB
                    if event_sub_thread_id:
                        # 子代理调用的工具，实时落库
                        await conversation_service.save_message(
                            conversation_id, "tool", str(display_content),
                            tool_name=tool_name, 
                            tool_call_id=actual_tool_call_id,
                            sub_thread_id=event_sub_thread_id
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
                        sub_thread_id=event_sub_thread_id
                    )

            # --- Step Done Marker ---
            elif kind == "on_chain_end":
                pass

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
