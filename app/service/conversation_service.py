import json
from io import TextIOWrapper
from pathlib import Path

from app.context.conversation_context import ConversationContext
from app.node import NodeType

CONVERSATIONS_DIR = "conversations"

RUNTIME_DIR = Path.cwd()


def save_conversation(context: ConversationContext):
    """
    保存会话
    文件名格式为: conversation_id.json
    如果文件已存在，将被覆盖
    """
    save_dir = RUNTIME_DIR / CONVERSATIONS_DIR
    save_dir.mkdir(parents=True, exist_ok=True)  # 创建目录，如果不存在
    filename = save_dir / f"{context.conversation_id}.json"

    data = {
        'conversation_id': context.conversation_id,
        'messages': context.messages_to_dict_list(),
        'current_node': context.current_node
    }

    # 写入JSON文件
    with open(filename, 'w', encoding='utf-8') as f:  # type: TextIOWrapper
        json.dump(data, f, ensure_ascii=False, indent=4)


def get_conversation_context(conversation_id: str) -> ConversationContext | None:
    filename = RUNTIME_DIR / CONVERSATIONS_DIR / f"{conversation_id}.json"
    if not filename.exists():
        return None
    with open(filename, 'r', encoding='utf-8') as f:  # type: TextIOWrapper
        data = json.load(f)
        context = ConversationContext(conversation_id=data['conversation_id'])
        context.dict_list_to_message(data['messages'])
        current_node = data['current_node']
        if current_node == NodeType.JAVA_DIAGNOSIS.value:
            context.current_node = NodeType.JAVA_DIAGNOSIS.value
        elif current_node == NodeType.SHELL.value:
            context.current_node = NodeType.SHELL.value
        else:
            context.current_node = NodeType.TRIAGE.value
        return context
