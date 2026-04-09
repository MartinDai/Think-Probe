from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse

from app.context.conversation_context import ConversationContext
from app.service import conversation_service, workflow_service

router = APIRouter(prefix="/api/conversations", tags=["Conversations"])


@router.get("")
async def list_conversations():
    """获取所有会话列表"""
    return {"conversations": conversation_service.list_conversations()}


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str):
    """获取特定会话的完整时间轴详情"""
    timeline = await conversation_service.get_conversation_timeline(conversation_id)
    if not timeline:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return timeline


@router.patch("/{conversation_id}")
async def update_conversation(conversation_id: str, request: Request):
    """更新会话元数据（如标题）"""
    data = await request.json()
    if not conversation_service.conversation_exists(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")

    updates = {}
    if "title" in data:
        updates["title"] = data["title"]

    if updates:
        conversation_service.update_metadata(conversation_id, updates)
    return {"status": "success"}


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """删除会话"""
    success = conversation_service.delete_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found or failed to delete")
    return {"status": "success"}


@router.post("/{conversation_id}/messages")
async def create_message(conversation_id: str, request: Request):
    """向会话发送消息并获取流式响应"""
    data = await request.json()
    messages = data.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="Messages are required")

    message_content = messages[-1].get("content", "")
    if not message_content:
        raise HTTPException(status_code=400, detail="Message content is required")

    context = ConversationContext(conversation_id)
    if conversation_service.conversation_exists(conversation_id):
        # 加载已有的主代理消息
        context.messages = await conversation_service.get_messages(conversation_id)

    return StreamingResponse(
        workflow_service.process_message(message_content, context),
        media_type="text/event-stream"
    )


@router.post("/{conversation_id}/stop")
async def stop_conversation(conversation_id: str):
    """停止会话生成"""
    from app.service import stop_service
    stop_service.set_stop_event(conversation_id)
    return {"status": "success"}
