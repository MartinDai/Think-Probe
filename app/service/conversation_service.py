import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from sqlalchemy import select, delete, desc, asc, update

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage

from app.utils.logger import logger
from app.store.database import get_session, Conversation, Message

CONVERSATIONS_DIR = "conversations"
RUNTIME_DIR = Path.cwd()

def _message_to_dict(msg: Message) -> dict:
    """Convert a DB Message to a serializable dict for the UI"""
    result = {
        "id": msg.id,
        "role": msg.role,
        "content": msg.content,
    }
    if msg.role == "ai":
        if msg.tool_calls:
            result["tool_calls"] = msg.tool_calls
        if msg.reasoning_content:
            result["reasoning_content"] = msg.reasoning_content
    elif msg.role == "tool":
        result["name"] = msg.tool_name
        result["tool_call_id"] = msg.tool_call_id
        if msg.sub_thread_id:
            result["sub_thread_id"] = msg.sub_thread_id
    return result

async def save_message(
    conversation_id: str, 
    role: str, 
    content: str, 
    tool_calls: list = None, 
    reasoning_content: str = None, 
    tool_name: str = None, 
    tool_call_id: str = None, 
    sub_thread_id: str = None
) -> Message:
    msg_id = str(uuid.uuid4())
    tool_calls_dict = tool_calls if tool_calls else None
       
    new_message = Message(
        id=msg_id,
        conversation_id=conversation_id,
        role=role,
        content=content,
        tool_calls=tool_calls_dict,
        reasoning_content=reasoning_content,
        tool_name=tool_name,
        tool_call_id=tool_call_id, # for standard tool calling
        sub_thread_id=sub_thread_id # for identifying sub-agent threads OR marking a message as BELONGING to a sub-thread
    )
    
    async with get_session() as session:
        session.add(new_message)
        # 顺便更新会话时间
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        res = await session.execute(stmt)
        conv = res.scalar_one_or_none()
        if conv:
            conv.updated_at = datetime.utcnow()
    return new_message

async def update_message_content(conversation_id: str, tool_call_id: str, content: str) -> bool:
    """Update the content of an existing message (usually an anchor)"""
    async with get_session() as session:
        stmt = update(Message).where(
            Message.conversation_id == conversation_id,
            Message.tool_call_id == tool_call_id
        ).values(content=content)
        result = await session.execute(stmt)
        
        # 同时更新会话的活跃时间
        stmt_conv = update(Conversation).where(Conversation.id == conversation_id).values(updated_at=datetime.utcnow())
        await session.execute(stmt_conv)
        
        return result.rowcount > 0

async def get_messages(conversation_id: str, thread_id: str = None) -> list[BaseMessage]:
    """
    Read messages for a specific thread from DB and convert to LangChain objects.
    """
    async with get_session() as session:
        if thread_id:
            stmt = select(Message).where(Message.conversation_id == conversation_id, Message.sub_thread_id == thread_id, Message.role.in_(["human", "ai"])).order_by(asc(Message.created_at))
        else:
            # Main thread messages: sub_thread_id specifies its thread location. None means main thread
            stmt = select(Message).where(Message.conversation_id == conversation_id, Message.sub_thread_id.is_(None)).order_by(asc(Message.created_at))
            
        result = await session.execute(stmt)
        db_msgs = result.scalars().all()
        
    langchain_msgs = []
    for db_m in db_msgs:
        if db_m.role == "human":
            langchain_msgs.append(HumanMessage(content=db_m.content))
        elif db_m.role == "ai":
            kwargs = {}
            if db_m.reasoning_content:
                kwargs["reasoning_content"] = db_m.reasoning_content
            langchain_msgs.append(AIMessage(content=db_m.content, tool_calls=db_m.tool_calls or [], additional_kwargs=kwargs))
        elif db_m.role == "tool":
            kwargs = {}
            if db_m.sub_thread_id: # meaning this tool SPAWNED a sub_thread, but it itself belongs to main thread
                kwargs["sub_thread_id"] = db_m.sub_thread_id
            langchain_msgs.append(ToolMessage(
                name=db_m.tool_name or "",
                content=db_m.content,
                tool_call_id=db_m.tool_call_id or "",
                additional_kwargs=kwargs
            ))
            
    return langchain_msgs

async def get_conversation_timeline(conversation_id: str) -> dict | None:
    """
    Build the full conversation timeline from DB.
    Recursively embeds sub-agent messages by following sub_thread_id linked in ToolMessages.
    """
    if not await conversation_exists(conversation_id):
        return None

    async with get_session() as session:
        # 获取该会话下的所有消息（按时间排序）
        stmt = select(Message).where(Message.conversation_id == conversation_id).order_by(asc(Message.created_at))
        result = await session.execute(stmt)
        all_msgs = result.scalars().all()

    records = []
    
    # 区分主线程消息和子线程消息
    # 主线程消息: sub_thread_id 是 null，或者是 ToolMessage (它的 sub_thread_id 代表它发起的线程)
    main_messages = []
    sub_message_map = {} # thread_id -> list[dict]
    
    for m in all_msgs:
        if m.role == "tool" and m.sub_thread_id and m.tool_name == "sub_task":
            # 这是一个指代子线程的工具消息，存在于主线程中
            main_messages.append(m)
        elif m.sub_thread_id:
            # 这是存在于子线程内部的消息 (human, ai, 或者普通的 tool 等)
            m_dict = _message_to_dict(m)
            if m.sub_thread_id not in sub_message_map:
                sub_message_map[m.sub_thread_id] = []
            sub_message_map[m.sub_thread_id].append(m_dict)
        else:
            # 主线程消息
            main_messages.append(m)

    # 构建 tool_call_id 到 tool_name 的索引，从主线程的 AI 消息中寻找
    tool_call_to_name = {}
    for m in main_messages:
        if m.role == "ai" and m.tool_calls:
            for tc in m.tool_calls:
                tc_id = tc.get('id') or tc.get('tool_call_id')
                if tc_id:
                    tool_call_to_name[tc_id] = tc.get('name')

    # 组装返回结果
    consumed_sub_threads = set()
    for m in main_messages:
        msg_dict = _message_to_dict(m)
        
        if m.role == "tool" and m.sub_thread_id and m.tool_name == "sub_task":
            # 将子线程里的消息塞进去
            if m.sub_thread_id in sub_message_map:
                msg_dict["sub_agent_messages"] = sub_message_map[m.sub_thread_id]
                consumed_sub_threads.add(m.sub_thread_id)
                
        records.append(msg_dict)

    # 兜底：处理 orphaned (孤儿) 子线程消息
    # 那些存在于 message 表中但主线程没有对应 transfer_to 锚点 (ToolMessage) 的消息
    # 我们利用已有的 AIMessage 中的 tool_call 信息来恢复其名称
    for thread_id, sub_msgs in sub_message_map.items():
        if thread_id not in consumed_sub_threads:
            parts = thread_id.split(":")
            tool_call_id = parts[-1] if parts else "unknown"
            
            # 优先从 AIMessage 的索引中找名字
            recovered_name = tool_call_to_name.get(tool_call_id, "sub_task")
                
            # 创建虚拟锚点以确保消息不丢失
            synthetic_anchor = {
                "id": f"synthetic_{thread_id}",
                "role": "tool",
                "content": "任务执行已被中断或发生异常 (日志已自动恢复)",
                "name": recovered_name,
                "tool_call_id": tool_call_id,
                "sub_thread_id": thread_id,
                "sub_agent_messages": sub_msgs
            }
            records.append(synthetic_anchor)

    return {
        "conversation_id": conversation_id,
        "messages": records,
    }

async def get_metadata(conversation_id: str) -> dict:
    """Get conversation metadata from DB"""
    async with get_session() as session:
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await session.execute(stmt)
        conv = result.scalar_one_or_none()
        if conv:
            return {
                "id": conv.id,
                "title": conv.title,
                "created_at": conv.created_at.isoformat(),
                "updated_at": conv.updated_at.isoformat()
            }
    return {}

async def update_metadata(conversation_id: str, metadata: dict):
    """Update conversation metadata in DB (Creates if not exists)"""
    async with get_session() as session:
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await session.execute(stmt)
        conv = result.scalar_one_or_none()
        
        if not conv:
            conv = Conversation(
                id=conversation_id,
                title=metadata.get("title", f"Chat {conversation_id[:8]}"),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            session.add(conv)
        else:
            if "title" in metadata:
                conv.title = metadata["title"]
            conv.updated_at = datetime.utcnow()

async def list_conversations() -> list[dict]:
    """List all available conversations from DB"""
    async with get_session() as session:
        stmt = select(Conversation).order_by(desc(Conversation.updated_at))
        result = await session.execute(stmt)
        convs = result.scalars().all()
        
        return [{
            "id": c.id,
            "title": c.title,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat()
        } for c in convs]

async def conversation_exists(conversation_id: str) -> bool:
    """Check if a conversation exists in DB"""
    async with get_session() as session:
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

async def delete_conversation(conversation_id: str) -> bool:
    """Delete the conversation from DB and also clean up Checkpointer Directory"""
    try:
        async with get_session() as session:
            # SQLite cascade is not guaranteed unless PRAGMA foreign_keys=ON
            # Delete messages first
            await session.execute(delete(Message).where(Message.conversation_id == conversation_id))
            await session.execute(delete(Conversation).where(Conversation.id == conversation_id))
        
        # Optionally, delete the physical old json file if it existed
        dir_path = RUNTIME_DIR / CONVERSATIONS_DIR / conversation_id
        if dir_path.exists():
            shutil.rmtree(dir_path)
        return True
    except Exception as e:
        logger.error(f"Failed to delete conversation {conversation_id}: {e}")
        return False

