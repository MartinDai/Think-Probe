from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field
from app.tools.terminal import get_thread_id, get_workspace_dir


MAX_PATCH_SIZE = 200_000
MAX_PATCH_FILES = 20
MAX_FILE_SIZE = 1_000_000


@dataclass
class Hunk:
    lines: list[str]


@dataclass
class PatchAction:
    action: Literal["update", "add", "delete"]
    path: str
    hunks: list[Hunk]


@dataclass
class PatchPlan:
    actions: list[PatchAction]


class ApplyPatchOperation(BaseModel):
    type: Literal["create_file", "update_file", "delete_file"] = Field(
        description="Patch operation type."
    )
    path: str = Field(
        description="Relative path within the current workspace."
    )
    diff: str = Field(
        default="",
        description=(
            "For update_file, provide one or more hunks in a unified-diff-like body. "
            "Each hunk starts with @@, and hunk lines use prefixes ' ', '-', '+'. "
            "For create_file, provide the full file content. "
            "For delete_file, leave this empty."
        ),
    )


class ApplyPatchInput(BaseModel):
    operation: ApplyPatchOperation = Field(
        description="Structured patch operation with type, path, and diff."
    )

def validate_and_get_abs_path(workspace_dir: Path, rel_file_path: str) -> Path:
    """校验路径安全并返回绝对路径，仅允许在项目工作区内的相对路径"""
    # 显式禁止绝对路径
    if rel_file_path.startswith("/") or rel_file_path.startswith("\\"):
        raise ValueError("Security Error: Absolute paths are not allowed. Please use relative paths.")
    
    # 显式禁止协议头
    if "://" in rel_file_path:
         raise ValueError("Security Error: Protocol-based paths are not allowed.")

    if ".." in rel_file_path:
        raise ValueError("Security Error: Path traversal ('..') is not allowed.")

    # 计算目标文件的绝对路径
    target_path = (workspace_dir / rel_file_path).resolve()
    
    # 确保目标路径仍在项目工作区内
    if not str(target_path).startswith(str(workspace_dir.resolve())):
        raise ValueError("Security Error: Access outside the project workspace is prohibited.")
    
    return target_path


def _read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    if len(raw) > MAX_FILE_SIZE:
        raise ValueError(f"File is too large to patch: {path.name}")

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"File is not valid UTF-8 text: {path.name}") from exc


def _parse_update_diff(path: str, diff: str) -> list[Hunk]:
    if len(diff) > MAX_PATCH_SIZE:
        raise ValueError(f"Patch diff exceeds max size of {MAX_PATCH_SIZE} characters.")

    lines = diff.splitlines(keepends=True)
    if not lines:
        raise ValueError(f"Update operation must include diff content: {path}")

    hunks: list[Hunk] = []
    current_hunk: list[str] | None = None

    for raw_line in lines:
        if raw_line.startswith("@@"):
            if current_hunk is not None:
                hunks.append(Hunk(lines=current_hunk))
            current_hunk = []
            continue

        if current_hunk is None:
            raise ValueError(f"Update diff must start each block with '@@': {path}")

        if raw_line[:1] not in {" ", "+", "-"}:
            raise ValueError(f"Invalid update hunk line: {raw_line.rstrip()}")
        current_hunk.append(raw_line)

    if current_hunk is not None:
        hunks.append(Hunk(lines=current_hunk))

    if not hunks:
        raise ValueError(f"Update operation must include at least one hunk: {path}")

    return hunks


def _build_plan(operation: ApplyPatchOperation) -> PatchPlan:
    path = operation.path
    diff = operation.diff

    if operation.type == "update_file":
        return PatchPlan(actions=[PatchAction(action="update", path=path, hunks=_parse_update_diff(path, diff))])

    if operation.type == "create_file":
        if len(diff) > MAX_PATCH_SIZE:
            raise ValueError(f"Patch diff exceeds max size of {MAX_PATCH_SIZE} characters.")
        return PatchPlan(actions=[PatchAction(action="add", path=path, hunks=[Hunk(lines=[f"+{line}" for line in diff.splitlines(keepends=True)])])])

    if operation.type == "delete_file":
        if diff.strip():
            raise ValueError("delete_file does not use diff content.")
        return PatchPlan(actions=[PatchAction(action="delete", path=path, hunks=[])])

    raise ValueError(f"Unsupported operation type: {operation.type}")


def _hunk_to_blocks(hunk: Hunk) -> tuple[str, str]:
    old_parts: list[str] = []
    new_parts: list[str] = []

    for line in hunk.lines:
        marker = line[:1]
        body = line[1:]
        if marker == " ":
            old_parts.append(body)
            new_parts.append(body)
        elif marker == "-":
            old_parts.append(body)
        elif marker == "+":
            new_parts.append(body)
        else:
            raise ValueError(f"Invalid hunk line marker: {line.rstrip()}")

    old_block = "".join(old_parts)
    new_block = "".join(new_parts)

    if not old_block and not new_block:
        raise ValueError("Empty hunk is not allowed.")

    return old_block, new_block


def _match_candidates(old_block: str, new_block: str) -> list[tuple[str, str]]:
    candidates = [(old_block, new_block)]

    if old_block:
        trimmed_old = old_block.strip("\n")
        if trimmed_old != old_block:
            leading = len(old_block) - len(old_block.lstrip("\n"))
            trailing = len(old_block) - len(old_block.rstrip("\n"))
            trimmed_new = new_block
            if leading:
                trimmed_new = trimmed_new[leading:] if len(trimmed_new) >= leading else trimmed_new
            if trailing:
                trimmed_new = trimmed_new[:-trailing] if len(trimmed_new) >= trailing else trimmed_new
            candidate = (trimmed_old, trimmed_new)
            if candidate not in candidates:
                candidates.append(candidate)

    return candidates


def _apply_update(text: str, action: PatchAction) -> str:
    updated = text
    cursor = 0

    for hunk in action.hunks:
        old_block, new_block = _hunk_to_blocks(hunk)
        match_index = -1
        chosen_old = old_block
        chosen_new = new_block

        for candidate_old, candidate_new in _match_candidates(old_block, new_block):
            if candidate_old:
                idx = updated.find(candidate_old, cursor)
                if idx == -1:
                    idx = updated.find(candidate_old)
            else:
                idx = cursor

            if idx != -1:
                match_index = idx
                chosen_old = candidate_old
                chosen_new = candidate_new
                break

        if match_index == -1:
            raise ValueError(
                f"Hunk did not match file contents for '{action.path}'. "
                "Use read_file to verify the latest file content before retrying."
            )

        updated = (
            updated[:match_index]
            + chosen_new
            + updated[match_index + len(chosen_old):]
        )
        cursor = match_index + len(chosen_new)

    return updated


def _build_add_file_content(action: PatchAction) -> str:
    if len(action.hunks) != 1:
        raise ValueError(f"Add action must contain exactly one content block: {action.path}")

    parts: list[str] = []
    for line in action.hunks[0].lines:
        if not line.startswith("+"):
            raise ValueError(f"Add file lines must start with '+': {action.path}")
        parts.append(line[1:])
    return "".join(parts)


def _prepare_patch_writes(workspace_dir: Path, plan: PatchPlan) -> tuple[dict[Path, str], dict[str, list[str]]]:
    writes: dict[Path, str] = {}
    summary = {"updated": [], "added": [], "deleted": []}

    for action in plan.actions:
        target_path = validate_and_get_abs_path(workspace_dir, action.path)

        if action.action == "update":
            if not target_path.exists():
                raise ValueError(f"File not found for update: {action.path}")
            if target_path.is_dir():
                raise ValueError(f"Cannot update a directory: {action.path}")
            current_text = _read_text_file(target_path)
            writes[target_path] = _apply_update(current_text, action)
            summary["updated"].append(action.path)
            continue

        if action.action == "add":
            if target_path.exists():
                raise ValueError(f"File already exists for add: {action.path}")
            writes[target_path] = _build_add_file_content(action)
            summary["added"].append(action.path)
            continue

        if action.action == "delete":
            if not target_path.exists():
                raise ValueError(f"File not found for delete: {action.path}")
            if target_path.is_dir():
                raise ValueError(f"Delete action does not support directories: {action.path}")
            _read_text_file(target_path)
            writes[target_path] = ""
            summary["deleted"].append(action.path)
            continue

        raise ValueError(f"Unsupported patch action: {action.action}")

    return writes, summary


@tool(
    args_schema=ApplyPatchInput,
    description=(
        "Apply a structured patch operation to text files in the current workspace. "
        "The input is an object with operation.type, operation.path, and operation.diff. "
        "Supported operation.type values are create_file, update_file, and delete_file. "
        "For update_file, operation.diff is a unified-diff-like body for a single file: "
        "each hunk starts with @@, and hunk lines use prefixes ' ', '-', '+'. "
        "For create_file, operation.diff is the full file content. "
        "For delete_file, operation.diff is empty. "
        "Example update_file diff:\n"
        "@@\n"
        "-print('old')\n"
        "+print('new')\n"
    ),
)
def apply_patch(operation: ApplyPatchOperation, config: RunnableConfig) -> str:
    """
    在项目工作区内应用结构化补丁操作。

    Args:
        operation (ApplyPatchOperation): 结构化补丁操作。
    """
    workspace_dir = get_workspace_dir(get_thread_id(config))

    try:
        plan = _build_plan(operation)
        writes, summary = _prepare_patch_writes(workspace_dir, plan)
        deleted_paths = {
            validate_and_get_abs_path(workspace_dir, action.path)
            for action in plan.actions
            if action.action == "delete"
        }

        for path, content in writes.items():
            if path in deleted_paths:
                path.unlink()
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        lines = ["Status: Success"]
        total = sum(len(items) for items in summary.values())
        lines.append(f"Files changed: {total}")
        for label, key in (("Updated", "updated"), ("Added", "added"), ("Deleted", "deleted")):
            for item in summary[key]:
                lines.append(f"{label}: {item}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {str(e)}"

@tool(description=(
    "在项目工作区内创建新文件或完全覆盖已有文件。"
    "适用于：创建全新的文件、需要完整替换文件所有内容时。"
    "不适用于：对现有文件进行局部修改（用 apply_patch，更安全且保留上下文）。"
))
def write_file(file_path: str, content: str, config: RunnableConfig, append: bool = False) -> str:
    """
    在项目工作区内写入文件。

    Args:
        file_path (str): 目标文件路径。必须使用【相对路径】（相对于当前会话的 workspace 根目录）。禁止以 '/' 开头。
        content (str): 要写入的文件内容。
        append (bool): 若为 True，则追加内容而非覆盖。默认 False。
    """
    workspace_dir = get_workspace_dir(get_thread_id(config))
    
    try:
        target_path = validate_and_get_abs_path(workspace_dir, file_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        mode = 'a' if append else 'w'
        with open(target_path, mode, encoding='utf-8') as f:
            f.write(content)
            
        return f"Successfully {'appended to' if append else 'written to'} {file_path}."
    except Exception as e:
        return f"Error: {str(e)}"

@tool(description=(
    "读取项目工作区内的文件内容。支持指定行号范围以减少大文件的读取量。"
    "适用于：查看代码内容、确认文件状态、为 apply_patch 操作做准备。"
    "不适用于：浏览目录结构（用 list_dir）、搜索文件内容（用 grep_search）。"
))
def read_file(file_path: str, config: RunnableConfig, start_line: int = 0, end_line: int = 0) -> str:
    """
    读取沙箱内的文件内容。

    Args:
        file_path (str): 要读取的文件路径。必须使用【相对路径】（相对于当前会话的 workspace 根目录）。禁止以 '/' 开头。
        start_line (int): 起始行号（1-indexed，含），0 表示从头开始。
        end_line (int): 结束行号（1-indexed，含），0 表示读到文件末尾。
    """
    workspace_dir = get_workspace_dir(get_thread_id(config))
    
    try:
        target_path = validate_and_get_abs_path(workspace_dir, file_path)
        
        if not target_path.exists():
            return f"Error: File {file_path} not found."
            
        if target_path.is_dir():
            return f"Error: {file_path} is a directory. Use list_dir to browse directory contents."
            
        with open(target_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        total_lines = len(lines)

        # 行号范围处理
        if start_line > 0 or end_line > 0:
            actual_start = max(1, start_line) if start_line > 0 else 1
            actual_end = min(total_lines, end_line) if end_line > 0 else total_lines

            if actual_start > total_lines:
                return f"Error: start_line ({actual_start}) exceeds total lines ({total_lines})."

            selected = lines[actual_start - 1:actual_end]
            header = f"File: {file_path} (lines {actual_start}-{actual_end} of {total_lines})\n"
            # 带行号的输出
            numbered = [f"{actual_start + i}: {line}" for i, line in enumerate(selected)]
            return header + "".join(numbered)
        else:
            return "".join(lines)

    except Exception as e:
        return f"Error: {str(e)}"
