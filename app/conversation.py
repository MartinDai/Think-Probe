import json
from io import TextIOWrapper

from app.agent.java_diagnosis_agent import JavaDiagnosisAgent
from app.agent.shell_agent import ShellAgent
from app.agent.triage_agent import TriageAgent
from app.config.config import RUNTIME_DIR
from app.context.conversation_context import ConversationContext

CONVERSATIONS_DIR = "conversations"


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
        'input_items': context.input_items,
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
        elif current_agent == "Shell Agent":
            context.current_agent = ShellAgent
        else:
            context.current_agent = TriageAgent
        return context
