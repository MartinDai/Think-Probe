import json
import math
import re
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.config.env_config import get_env_variable
from app.core.llm import COMPACTION_MODEL, invoke_with_retry
from app.utils.logger import logger


CONVERSATIONS_DIR = "conversations"
RUNTIME_DIR = Path.cwd()

DEFAULT_MAX_CONTEXT_TOKENS = int(get_env_variable("MAX_CONTEXT_TOKENS", "24000"))
DEFAULT_WARNING_RATIO = float(get_env_variable("CONTEXT_WARNING_RATIO", "0.7"))
DEFAULT_COMPACT_RATIO = float(get_env_variable("CONTEXT_COMPACT_RATIO", "0.85"))
DEFAULT_RECENT_MESSAGE_COUNT = int(get_env_variable("CONTEXT_RECENT_MESSAGE_COUNT", "6"))

SESSION_STATE_FILE = "session_state.json"
ROLLING_SUMMARY_FILE = "rolling_summary.json"
SUMMARY_VERSION = 1

CONSTRAINT_KEYWORDS = (
    "必须", "需要", "不要", "不能", "禁止", "务必", "only", "must", "should", "avoid", "do not", "don't",
)
DECISION_KEYWORDS = ("决定", "采用", "改为", "将使用", "方案", "use ", "will use", "decide", "chosen", "选择")
REJECTED_KEYWORDS = (
    "不要", "不能", "不采用", "放弃", "reject", "won't use", "不用", "弃用",
)
FAILURE_KEYWORDS = (
    "error", "failed", "exception", "traceback", "timeout", "失败", "错误", "异常", "超时",
)
NEXT_STEP_KEYWORDS = (
    "下一步", "接下来", "后续", "next step", "next:", "todo", "plan",
)
OPEN_QUESTION_KEYWORDS = (
    "待确认", "需要确认", "未确定", "open question", "question",
)
SUMMARY_FIELDS = (
    "task",
    "constraints",
    "decisions",
    "rejected_options",
    "open_questions",
    "recent_failures",
    "artifacts",
    "next_steps",
)
SUMMARY_EXTRACTION_PROMPT = """你是一个会话压缩器。你的任务是把旧消息提取为结构化执行摘要，供后续 agent 继续工作。

要求：
1. 只输出合法 JSON，不要输出 markdown，不要输出解释。
2. 必须遵循给定 schema，缺失字段使用空字符串、空数组或空对象。
3. 只保留后续执行真正需要的信息，删除寒暄、重复措辞和无关细节。
4. 优先保留：当前任务、用户硬约束、已做决策、被否决方案、未解决问题、失败原因、关键产物、下一步。
5. 如果历史摘要与新消息冲突，以新消息为准；但不要丢掉仍然有效的旧约束。
6. 每个数组尽量简洁，单项最好一句话。

输出 schema：
{
  "task": "string",
  "constraints": ["string"],
  "decisions": ["string"],
  "rejected_options": ["string"],
  "open_questions": ["string"],
  "recent_failures": ["string"],
  "artifacts": [{"type": "string", "id": "string", "why_it_matters": "string"}],
  "next_steps": ["string"]
}
"""


def _conversation_dir(conversation_id: str) -> Path:
    path = RUNTIME_DIR / CONVERSATIONS_DIR / conversation_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _session_state_path(conversation_id: str) -> Path:
    return _conversation_dir(conversation_id) / SESSION_STATE_FILE


def _rolling_summary_path(conversation_id: str) -> Path:
    return _conversation_dir(conversation_id) / ROLLING_SUMMARY_FILE


def _default_session_state(conversation_id: str) -> dict:
    return {
        "conversation_id": conversation_id,
        "status": "normal",
        "max_context_tokens": DEFAULT_MAX_CONTEXT_TOKENS,
        "warning_ratio": DEFAULT_WARNING_RATIO,
        "compact_ratio": DEFAULT_COMPACT_RATIO,
        "recent_message_count": DEFAULT_RECENT_MESSAGE_COUNT,
        "estimated_total_tokens": 0,
        "kept_message_count": 0,
        "compacted_message_count": 0,
        "should_compact": False,
        "last_summary_at": None,
        "last_compacted_at": None,
        "updated_at": None,
    }


def _default_rolling_summary() -> dict:
    return {
        "summary_version": SUMMARY_VERSION,
        "task": "",
        "constraints": [],
        "decisions": [],
        "rejected_options": [],
        "open_questions": [],
        "recent_failures": [],
        "artifacts": [],
        "next_steps": [],
        "updated_at": None,
    }


def load_session_state(conversation_id: str) -> dict:
    path = _session_state_path(conversation_id)
    if not path.exists():
        return _default_session_state(conversation_id)
    try:
        return {**_default_session_state(conversation_id), **json.loads(path.read_text(encoding="utf-8"))}
    except Exception as exc:
        logger.warning("Failed to load session state for %s: %s", conversation_id, exc)
        return _default_session_state(conversation_id)


def save_session_state(conversation_id: str, state: dict) -> None:
    payload = {**_default_session_state(conversation_id), **state}
    payload["updated_at"] = _utcnow_iso()
    _session_state_path(conversation_id).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_rolling_summary(conversation_id: str) -> dict:
    path = _rolling_summary_path(conversation_id)
    if not path.exists():
        return _default_rolling_summary()
    try:
        return {**_default_rolling_summary(), **json.loads(path.read_text(encoding="utf-8"))}
    except Exception as exc:
        logger.warning("Failed to load rolling summary for %s: %s", conversation_id, exc)
        return _default_rolling_summary()


def save_rolling_summary(conversation_id: str, summary: dict) -> None:
    payload = {**_default_rolling_summary(), **summary}
    payload["updated_at"] = _utcnow_iso()
    _rolling_summary_path(conversation_id).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def _normalize_content(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("text", ""))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    return str(content)


def estimate_message_tokens(message: BaseMessage) -> int:
    payload = [_normalize_content(message.content)]
    if isinstance(message, AIMessage):
        payload.append(json.dumps(message.tool_calls or [], ensure_ascii=False))
        payload.append(_normalize_content(message.additional_kwargs.get("reasoning_content")))
    if isinstance(message, ToolMessage):
        payload.append(message.name or "")
        payload.append(message.tool_call_id or "")
    return estimate_text_tokens("\n".join(part for part in payload if part)) + 12


def estimate_messages_tokens(messages: list[BaseMessage]) -> int:
    return sum(estimate_message_tokens(message) for message in messages)


def _split_candidates(text: str) -> list[str]:
    chunks = re.split(r"[\n\r]+|(?<=[。！？!?])", text)
    return [_clean_line(chunk) for chunk in chunks if _clean_line(chunk)]


def _clean_line(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip(" -•\t")


def _truncate(text: str, limit: int = 180) -> str:
    text = _clean_line(text)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _message_role(message: BaseMessage) -> str:
    if isinstance(message, HumanMessage):
        return "user"
    if isinstance(message, AIMessage):
        return "assistant"
    if isinstance(message, ToolMessage):
        return f"tool:{message.name or 'unknown'}"
    return "message"


def _serialize_message(message: BaseMessage) -> dict:
    payload = {
        "role": _message_role(message),
        "content": _normalize_content(message.content),
    }
    if isinstance(message, AIMessage) and message.tool_calls:
        payload["tool_calls"] = message.tool_calls
    if isinstance(message, AIMessage):
        reasoning = _normalize_content(message.additional_kwargs.get("reasoning_content"))
        if reasoning:
            payload["reasoning_content"] = reasoning
    if isinstance(message, ToolMessage):
        payload["tool_call_id"] = message.tool_call_id or ""
    return payload


def _append_unique(items: list, value, *, limit: int, key=None) -> None:
    value_key = key(value) if key else value
    existing = {key(item) if key else item for item in items}
    if value_key in existing:
        return
    items.append(value)
    if len(items) > limit:
        del items[0 : len(items) - limit]


def _normalize_summary_payload(payload: dict, existing_summary: dict | None = None) -> dict:
    existing = deepcopy(existing_summary or _default_rolling_summary())
    normalized = _default_rolling_summary()

    task = payload.get("task")
    normalized["task"] = _truncate(task, 240) if isinstance(task, str) and task.strip() else existing.get("task", "")

    for field in ("constraints", "decisions", "rejected_options", "open_questions", "recent_failures", "next_steps"):
        items = payload.get(field, [])
        merged = list(existing.get(field, []))
        if isinstance(items, list):
            for item in items:
                if isinstance(item, str) and _clean_line(item):
                    _append_unique(merged, _truncate(item), limit=10 if field != "next_steps" else 8)
        normalized[field] = merged

    merged_artifacts = deepcopy(existing.get("artifacts", []))
    artifacts = payload.get("artifacts", [])
    if isinstance(artifacts, list):
        for item in artifacts:
            if not isinstance(item, dict):
                continue
            artifact = {
                "type": _truncate(str(item.get("type", "artifact")), 40) or "artifact",
                "id": _truncate(str(item.get("id", "unknown")), 80) or "unknown",
                "why_it_matters": _truncate(str(item.get("why_it_matters", "")), 160),
            }
            _append_unique(
                merged_artifacts,
                artifact,
                limit=8,
                key=lambda value: (value.get("type"), value.get("id"), value.get("why_it_matters")),
            )
    normalized["artifacts"] = merged_artifacts
    normalized["summary_version"] = SUMMARY_VERSION
    normalized["updated_at"] = _utcnow_iso()
    return normalized


def _extract_json_object(text: str) -> dict | None:
    if not text:
        return None
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        return None


def _message_text(message: BaseMessage) -> str:
    text = _normalize_content(message.content)
    if isinstance(message, AIMessage):
        reasoning = _normalize_content(message.additional_kwargs.get("reasoning_content"))
        if reasoning:
            text = f"{text}\n{reasoning}".strip()
    return _truncate(text, 500)


def _build_summary_input(messages: list[BaseMessage], existing_summary: dict) -> str:
    history_payload = {
        "existing_summary": {field: existing_summary.get(field) for field in SUMMARY_FIELDS},
        "messages": [_serialize_message(message) for message in messages],
    }
    return json.dumps(history_payload, ensure_ascii=False, indent=2)


def _generate_summary_with_llm(messages: list[BaseMessage], existing_summary: dict) -> dict | None:
    system_message = SystemMessage(content=SUMMARY_EXTRACTION_PROMPT)
    user_message = HumanMessage(
        content="请基于以下历史摘要和待压缩消息，生成新的结构化执行摘要 JSON：\n"
        + _build_summary_input(messages, existing_summary)
    )
    try:
        response = invoke_with_retry(COMPACTION_MODEL, [system_message, user_message])
    except Exception as exc:
        logger.warning("Compaction model failed, falling back to heuristic summary: %s", exc)
        return None

    payload = _extract_json_object(_normalize_content(getattr(response, "content", "")))
    if payload is None:
        logger.warning("Compaction model returned invalid JSON, falling back to heuristic summary.")
        return None
    return _normalize_summary_payload(payload, existing_summary)


def _extract_latest_task(messages: list[BaseMessage], fallback: str) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            text = _truncate(_message_text(message), 240)
            if text:
                return text
    return fallback


def _collect_constraints(messages: list[BaseMessage], existing: list[str]) -> list[str]:
    collected = list(existing)
    for message in messages:
        if not isinstance(message, HumanMessage):
            continue
        for chunk in _split_candidates(_message_text(message)):
            lowered = chunk.lower()
            if any(keyword in chunk for keyword in CONSTRAINT_KEYWORDS) or any(
                keyword in lowered for keyword in CONSTRAINT_KEYWORDS if keyword.isascii()
            ):
                _append_unique(collected, _truncate(chunk), limit=10)
    return collected


def _collect_decisions(messages: list[BaseMessage], existing: list[str]) -> list[str]:
    collected = list(existing)
    for message in messages:
        if not isinstance(message, (HumanMessage, AIMessage)):
            continue
        for chunk in _split_candidates(_message_text(message)):
            lowered = chunk.lower()
            if "?" in chunk or "？" in chunk:
                continue
            if any(keyword in chunk for keyword in DECISION_KEYWORDS) or any(
                keyword in lowered for keyword in DECISION_KEYWORDS if keyword.isascii()
            ):
                _append_unique(collected, _truncate(chunk), limit=10)
    return collected


def _collect_rejections(messages: list[BaseMessage], existing: list[str]) -> list[str]:
    collected = list(existing)
    for message in messages:
        if not isinstance(message, (HumanMessage, AIMessage)):
            continue
        for chunk in _split_candidates(_message_text(message)):
            lowered = chunk.lower()
            if any(keyword in chunk for keyword in REJECTED_KEYWORDS) or any(
                keyword in lowered for keyword in REJECTED_KEYWORDS if keyword.isascii()
            ):
                _append_unique(collected, _truncate(chunk), limit=10)
    return collected


def _collect_open_questions(messages: list[BaseMessage], existing: list[str]) -> list[str]:
    collected = list(existing)
    for message in messages:
        if not isinstance(message, (HumanMessage, AIMessage)):
            continue
        for chunk in _split_candidates(_message_text(message)):
            lowered = chunk.lower()
            if chunk.endswith(("?", "？")) or any(keyword in chunk for keyword in OPEN_QUESTION_KEYWORDS) or any(
                keyword in lowered for keyword in OPEN_QUESTION_KEYWORDS if keyword.isascii()
            ):
                _append_unique(collected, _truncate(chunk), limit=10)
    return collected


def _collect_recent_failures(messages: list[BaseMessage], existing: list[str]) -> list[str]:
    collected = list(existing)
    for message in messages:
        text = _message_text(message)
        lowered = text.lower()
        if any(keyword in text for keyword in FAILURE_KEYWORDS) or any(
            keyword in lowered for keyword in FAILURE_KEYWORDS if keyword.isascii()
        ):
            role = "tool" if isinstance(message, ToolMessage) else "assistant" if isinstance(message, AIMessage) else "user"
            _append_unique(collected, f"{role}: {_truncate(text, 200)}", limit=10)
    return collected


def _collect_artifacts(messages: list[BaseMessage], existing: list[dict]) -> list[dict]:
    collected = deepcopy(existing)
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        artifact = {
            "type": "tool",
            "id": message.name or "tool",
            "why_it_matters": _truncate(_message_text(message), 120),
        }
        _append_unique(
            collected,
            artifact,
            limit=8,
            key=lambda item: (item.get("type"), item.get("id"), item.get("why_it_matters")),
        )
    return collected


def _collect_next_steps(messages: list[BaseMessage], existing: list[str]) -> list[str]:
    collected = list(existing)
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for chunk in _split_candidates(_message_text(message)):
            lowered = chunk.lower()
            if any(keyword in chunk for keyword in NEXT_STEP_KEYWORDS) or any(
                keyword in lowered for keyword in NEXT_STEP_KEYWORDS if keyword.isascii()
            ):
                _append_unique(collected, _truncate(chunk), limit=8)
    return collected


def summarize_messages(messages: list[BaseMessage], existing_summary: dict | None = None) -> dict:
    summary = deepcopy(existing_summary or _default_rolling_summary())
    if not messages:
        return summary

    llm_summary = _generate_summary_with_llm(messages, summary)
    if llm_summary is not None:
        return llm_summary

    summary["task"] = _extract_latest_task(messages, summary.get("task", ""))
    summary["constraints"] = _collect_constraints(messages, summary.get("constraints", []))
    summary["decisions"] = _collect_decisions(messages, summary.get("decisions", []))
    summary["rejected_options"] = _collect_rejections(messages, summary.get("rejected_options", []))
    summary["open_questions"] = _collect_open_questions(messages, summary.get("open_questions", []))
    summary["recent_failures"] = _collect_recent_failures(messages, summary.get("recent_failures", []))
    summary["artifacts"] = _collect_artifacts(messages, summary.get("artifacts", []))
    summary["next_steps"] = _collect_next_steps(messages, summary.get("next_steps", []))
    summary["summary_version"] = SUMMARY_VERSION
    summary["updated_at"] = _utcnow_iso()
    return summary


def prepare_messages_for_model(conversation_id: str, messages: list[BaseMessage]) -> list[BaseMessage]:
    state = load_session_state(conversation_id)
    max_context_tokens = int(state.get("max_context_tokens") or DEFAULT_MAX_CONTEXT_TOKENS)
    warning_threshold = math.floor(max_context_tokens * float(state.get("warning_ratio") or DEFAULT_WARNING_RATIO))
    compact_threshold = math.floor(max_context_tokens * float(state.get("compact_ratio") or DEFAULT_COMPACT_RATIO))
    recent_message_count = int(state.get("recent_message_count") or DEFAULT_RECENT_MESSAGE_COUNT)

    total_tokens = estimate_messages_tokens(messages)
    status = "normal"
    if total_tokens >= compact_threshold:
        status = "compacted"
    elif total_tokens >= warning_threshold:
        status = "warning"

    recent_messages = messages[-recent_message_count:] if recent_message_count > 0 else list(messages)
    compacted_messages = messages[:-recent_message_count] if recent_message_count > 0 else []

    next_state = {
        **state,
        "status": status,
        "estimated_total_tokens": total_tokens,
        "kept_message_count": len(recent_messages) if status == "compacted" else len(messages),
        "compacted_message_count": len(compacted_messages) if status == "compacted" else 0,
        "should_compact": status == "compacted",
    }

    if status in {"warning", "compacted"} and compacted_messages:
        current_summary = load_rolling_summary(conversation_id)
        next_summary = summarize_messages(compacted_messages, current_summary)
        save_rolling_summary(conversation_id, next_summary)
        next_state["last_summary_at"] = _utcnow_iso()

    if status == "compacted" and compacted_messages:
        next_state["last_compacted_at"] = _utcnow_iso()
        save_session_state(conversation_id, next_state)
        return recent_messages

    save_session_state(conversation_id, next_state)
    return messages


def _render_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items if item)


def build_compaction_prompt(conversation_id: str) -> str:
    state = load_session_state(conversation_id)
    summary = load_rolling_summary(conversation_id)

    has_summary = any(
        summary.get(field)
        for field in SUMMARY_FIELDS
    )
    if not has_summary:
        return ""

    parts = [
        "\n\n---\n# Conversation Memory",
        f"- 上下文状态: {state.get('status', 'normal')}",
        f"- 估算历史 token: {state.get('estimated_total_tokens', 0)} / {state.get('max_context_tokens', DEFAULT_MAX_CONTEXT_TOKENS)}",
    ]

    if summary.get("task"):
        parts.append("## 当前任务\n" + summary["task"])
    if summary.get("constraints"):
        parts.append("## 用户约束\n" + _render_list(summary["constraints"]))
    if summary.get("decisions"):
        parts.append("## 已做决策\n" + _render_list(summary["decisions"]))
    if summary.get("rejected_options"):
        parts.append("## 已否决方案\n" + _render_list(summary["rejected_options"]))
    if summary.get("open_questions"):
        parts.append("## 未解决问题\n" + _render_list(summary["open_questions"]))
    if summary.get("recent_failures"):
        parts.append("## 最近失败\n" + _render_list(summary["recent_failures"]))
    if summary.get("artifacts"):
        artifact_lines = [
            f"- [{artifact.get('type', 'artifact')}] {artifact.get('id', 'unknown')}: {artifact.get('why_it_matters', '')}"
            for artifact in summary["artifacts"]
        ]
        parts.append("## 相关产物\n" + "\n".join(artifact_lines))
    if summary.get("next_steps"):
        parts.append("## 建议下一步\n" + _render_list(summary["next_steps"]))

    parts.append("请把以上内容视为经过压缩保留的工作记忆；若与最近消息冲突，以最近消息和用户最新要求为准。")
    return "\n".join(parts)


def reset_compaction_state(conversation_id: str) -> None:
    for path in (_session_state_path(conversation_id), _rolling_summary_path(conversation_id)):
        if path.exists():
            path.unlink()
