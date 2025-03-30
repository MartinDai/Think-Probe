import ast
import json
from io import TextIOWrapper

from agents import TResponseInputItem
from openai.types.responses import EasyInputMessageParam

from app.agent.java_diagnosis_agent import JavaDiagnosisAgent
from app.agent.triage_agent import TriageAgent
from app.config.config import RUNTIME_DIR
from app.context.conversation_context import ConversationContext

CONVERSATIONS_DIR = "conversations"

TOOL_TYPES = [
    "function_call",
]


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
        'input_items': _remove_tool_types_from_input(context.input_items),
        'current_agent': str(context.current_agent.name)
    }

    # 写入JSON文件
    with open(filename, 'w', encoding='utf-8') as f:  # type: TextIOWrapper
        json.dump(data, f, ensure_ascii=False, indent=4)


def find_conversation(conversation_id: str) -> ConversationContext | None:
    filename = RUNTIME_DIR / CONVERSATIONS_DIR / f"{conversation_id}.json"
    if not filename.exists():
        return None
    with open(filename, 'r', encoding='utf-8') as f:  # type: TextIOWrapper
        data = json.load(f)
        context = ConversationContext(conversation_id=data['conversation_id'])
        context.input_items = data['input_items']
        current_agent = data['current_agent']
        if current_agent == "Java Diagnosis Agent":
            context.current_agent = JavaDiagnosisAgent
        else:
            context.current_agent = TriageAgent
        return context


def _remove_tool_types_from_input(items: list[TResponseInputItem]) -> list[TResponseInputItem]:
    """Remove tool-related items from the input list.

    Args:
        items: List of response input items to filter.

    Returns:
        Filtered list excluding tool-related types.
    """
    result = []
    for item in items:
        # 跳过工具相关的项
        if item.get("type") in TOOL_TYPES:
            continue

        # 统一转换成 EasyInputMessageParam
        transformed_item = _transform_item(item)
        if transformed_item is not None:
            result.append(transformed_item)

    return result


def _transform_item(item: TResponseInputItem) -> EasyInputMessageParam | None:
    """Transform an item into EasyInputMessageParam type."""

    role = item.get("role")
    valid_roles: set = {"user", "assistant", "tool"}
    if role not in valid_roles:
        role = "assistant"

    # 处理 content
    if item.get("type") == "function_call_output":
        content = item.get("output")
        content_dict = ast.literal_eval(content)  # 转换为字典

        if 'assistant' in content_dict:
            return None
        else:
            role = "tool"
            content = content_dict['tool']
    else:
        content = item.get("content")
        if isinstance(content, list) and len(content) > 0 and "text" in content[0]:
            # 如果 content 是列表，且第一个元素有 text 键，提取 text
            content = content[0]["text"]

    return EasyInputMessageParam(role=role, content=content)
