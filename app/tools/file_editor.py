import os
from pathlib import Path
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from app.tools.terminal import get_workspace_dir, get_last_cwd

def validate_and_get_abs_path(workspace_dir: Path, rel_file_path: str) -> Path:
    """校验路径安全并返回绝对路径，仅允许在工作空间内的相对路径"""
    # 显式禁止绝对路径
    if rel_file_path.startswith("/") or rel_file_path.startswith("\\"):
        raise ValueError("Security Error: Absolute paths are not allowed. Please use relative paths.")
    
    # 显式禁止协议头
    if "://" in rel_file_path:
         raise ValueError("Security Error: Protocol-based paths are not allowed.")

    if ".." in rel_file_path:
        raise ValueError("Security Error: Path traversal ('..') is not allowed.")
    
    # 获取当前会话的工作目录 (CWD)
    current_rel_cwd = get_last_cwd(workspace_dir)
    actual_cwd = (workspace_dir / current_rel_cwd).resolve()
    
    # 计算目标文件的绝对路径
    target_path = (actual_cwd / rel_file_path).resolve()
    
    # 确保目标路径仍在会话特定的子目录内
    if not str(target_path).startswith(str(workspace_dir.resolve())):
        raise ValueError("Security Error: Access outside the workspace is prohibited.")
    
    return target_path

def get_thread_id(config: RunnableConfig) -> str:
    """从配置中提取 thread_id"""
    if "configurable" in config:
        return config["configurable"].get("thread_id", "default_session")
    return "default_session"

@tool(description=(
    "在沙箱工作空间内创建新文件或完全覆盖已有文件。"
    "适用于：创建全新的文件、需要完整替换文件所有内容时。"
    "不适用于：对现有文件进行局部修改（用 edit_file，更安全且保留上下文）。"
))
def write_file(file_path: str, content: str, config: RunnableConfig, append: bool = False) -> str:
    """
    在工作空间内写入文件。

    Args:
        file_path (str): 目标文件路径。必须使用【相对路径】（相对于当前工作目录）。禁止以 '/' 开头。
        content (str): 要写入的文件内容。
        append (bool): 若为 True，则追加内容而非覆盖。默认 False。
    """
    thread_id = get_thread_id(config)
    workspace_dir = get_workspace_dir(thread_id)
    
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
    "对沙箱工作空间中的已有文件进行精确的字符串替换。"
    "适用于：修改代码中的特定片段、更新配置值、局部重构——文件其余部分保持不变。"
    "不适用于：创建新文件（用 write_file）、完整替换文件内容（用 write_file）。"
    "前置条件：使用前必须先通过 read_file 确认文件当前内容，确保 old_content 精确匹配（含缩进）。"
))
def edit_file(file_path: str, old_content: str, new_content: str, config: RunnableConfig) -> str:
    """
    搜索并替换文件中的精确字符串。

    Args:
        file_path (str): 目标文件路径。必须使用【相对路径】（相对于当前工作目录）。禁止以 '/' 开头。
        old_content (str): 要被替换的原始内容，必须与文件中的文本精确匹配（包含缩进和换行）。
        new_content (str): 替换后的新内容。
    """
    thread_id = get_thread_id(config)
    workspace_dir = get_workspace_dir(thread_id)
    
    try:
        target_path = validate_and_get_abs_path(workspace_dir, file_path)
        if not target_path.exists():
            return f"Error: File {file_path} not found."
            
        with open(target_path, 'r', encoding='utf-8') as f:
            data = f.read()
            
        if old_content not in data:
            return f"Error: Content to replace not found. Use read_file to verify current file content first."
            
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(data.replace(old_content, new_content))
            
        return f"Successfully updated {file_path}."
    except Exception as e:
        return f"Error: {str(e)}"

@tool(description=(
    "从沙箱工作空间中删除指定的文件或目录。"
    "适用于：清理不需要的文件、删除临时产物。"
    "注意：此操作不可逆。使用前请确认路径正确。"
))
def delete_file(file_path: str, config: RunnableConfig) -> str:
    """
    删除沙箱内的文件或目录。

    Args:
        file_path (str): 要删除的文件或目录路径。必须使用【相对路径】（相对于当前工作目录）。禁止以 '/' 开头。
    """
    thread_id = get_thread_id(config)
    workspace_dir = get_workspace_dir(thread_id)
    
    try:
        target_path = validate_and_get_abs_path(workspace_dir, file_path)
        if not target_path.exists():
            return f"Error: File {file_path} not found."
            
        if target_path.is_dir():
            import shutil
            shutil.rmtree(target_path)
        else:
            os.remove(target_path)
        return f"Successfully deleted {file_path}."
    except Exception as e:
        return f"Error: {str(e)}"

@tool(description=(
    "读取工作空间内的文件内容。支持指定行号范围以减少大文件的读取量。"
    "适用于：查看代码内容、确认文件状态、为 edit_file 操作做准备。"
    "不适用于：浏览目录结构（用 list_dir）、搜索文件内容（用 grep_search）。"
))
def read_file(file_path: str, config: RunnableConfig, start_line: int = 0, end_line: int = 0) -> str:
    """
    读取沙箱内的文件内容。

    Args:
        file_path (str): 要读取的文件路径。必须使用【相对路径】（相对于当前工作目录）。禁止以 '/' 开头。
        start_line (int): 起始行号（1-indexed，含），0 表示从头开始。
        end_line (int): 结束行号（1-indexed，含），0 表示读到文件末尾。
    """
    thread_id = get_thread_id(config)
    workspace_dir = get_workspace_dir(thread_id)
    
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
