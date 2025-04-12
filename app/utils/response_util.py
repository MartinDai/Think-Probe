import uuid
from datetime import datetime


def create_chunk(conversation_id=None, content=None, role=None, model=None, finish=False):
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
        chunk["choices"][0]["delta"] = {"role": role, "content": content}

    return chunk


def create_block(conversation_id=None, content=None, role=None, model=None):
    block = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:10]}",  # 生成随机 ID
        "object": "chat.completion.block",
        "conversation_id": conversation_id,
        "created": int(datetime.now().timestamp()),  # 时间戳
        "model": model,
        "choices": [{
            "delta": {
                "role": role,
                "content": content
            },
        }]
    }
    return block
