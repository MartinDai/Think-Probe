from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.context.conversation_context import ConversationContext
from app.service import conversation_service, workflow_service

chat_completions_router = APIRouter(prefix="")


@chat_completions_router.post("/v1/chat/completions")
async def chat_completion(request: Request):
    data = await request.json()
    conversation_id = data.get("conversation_id", "")
    message = data.get("messages", [{}])[-1].get("content", "")

    context = ConversationContext(conversation_id)
    if conversation_service.conversation_exists(conversation_id):
        # Load existing orchestrator messages from JSONL
        context.messages = conversation_service.get_messages(conversation_id, "orchestrator")

    return StreamingResponse(workflow_service.process_message(message, context),
                             media_type="text/event-stream")


@chat_completions_router.get("/v1/conversation/{conversation_id}/timeline")
async def get_timeline(conversation_id: str):
    timeline = conversation_service.get_conversation_timeline(conversation_id)
    if not timeline:
        return {"error": "Conversation not found"}
    return timeline

