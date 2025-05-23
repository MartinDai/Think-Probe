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

    conversation_context = conversation_service.get_conversation_context(conversation_id)
    if conversation_context is None:
        conversation_context = ConversationContext(conversation_id)
    return StreamingResponse(workflow_service.process_message(message, conversation_context),
                             media_type="text/event-stream")
