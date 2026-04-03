import uuid
from datetime import datetime


def create_chunk(conversation_id=None, content=None, reasoning_content=None, role=None, model=None, finish=False):
    chunk = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:10]}",  # 生成随机 ID
        "object": "chat.completion.chunk",
        "conversation_id": conversation_id,
        "created": int(datetime.now().timestamp()),  # 时间戳
        "model": model,
        "choices": [{
            "delta": {},
            "finish_reason": None,
        }]
    }
    if finish:
        chunk["choices"][0]["finish_reason"] = "stop"
    else:
        delta = {"role": role}
        if content is not None:
            delta["content"] = content
        if reasoning_content is not None:
            delta["reasoning_content"] = reasoning_content
        chunk["choices"][0]["delta"] = delta

    return chunk


def create_step_done(conversation_id=None):
    chunk = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:10]}",  # 生成随机 ID
        "object": "chat.completion.step.done",
        "conversation_id": conversation_id,
        "created": int(datetime.now().timestamp()),  # 时间戳
        "model": "none",
        "choices": [{
            "index": 0,
            "delta": {"role": "assistant", "content": "\n"},
            "finish_reason": None,
        }]
    }
    return chunk
