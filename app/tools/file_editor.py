import os
from pathlib import Path
from typing import Optional
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from app.tools.terminal import get_workspace_dir, get_last_cwd

def validate_and_get_abs_path(workspace_dir: Path, rel_file_path: str) -> Path:
    """校验路径安全并返回绝对路径"""
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

@tool(description="在沙箱工作空间内创建或追加文件内容。")
def write_file(file_path: str, content: str, config: RunnableConfig, append: bool = False) -> str:
    """
    在工作空间内写入文件。
    """
    thread_id = get_thread_id(config)
    workspace_dir = get_workspace_dir(thread_id)
    
    try:
        target_path = validate_and_get_abs_path(workspace_dir, file_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        mode = 'a' if append else 'w'
        with open(target_path, mode, encoding='utf-8') as f:
            f.write(content)
            
        return f"Successfully {'appended to' if append else 'written to'} {file_path} (Session: {thread_id})."
    except Exception as e:
        return f"Error: {str(e)}"

@tool(description="在沙箱工作空间的文件中替换特定内容。")
def replace_file_content(file_path: str, old_content: str, new_content: str, config: RunnableConfig) -> str:
    """
    搜索并替换文件中的字符串。
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
            return f"Error: Content to replace not found."
            
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(data.replace(old_content, new_content))
            
        return f"Successfully updated {file_path} (Session: {thread_id})."
    except Exception as e:
        return f"Error: {str(e)}"

@tool(description="从沙箱工作空间中安全删除指定文件。")
def delete_file(file_path: str, config: RunnableConfig) -> str:
    """
    删除沙箱内的文件。
    """
    thread_id = get_thread_id(config)
    workspace_dir = get_workspace_dir(thread_id)
    
    try:
        target_path = validate_and_get_abs_path(workspace_dir, file_path)
        if not target_path.exists():
            return f"Error: File {file_path} not found in session {thread_id}."
            
        if target_path.is_dir():
            import shutil
            shutil.rmtree(target_path)
        else:
            os.remove(target_path)
        return f"Successfully deleted {file_path} (Session: {thread_id})."
    except Exception as e:
        return f"Error: {str(e)}"

@tool(description="读取工作空间内的文件内容。")
def read_file(file_path: str, config: RunnableConfig) -> str:
    """
    读取沙箱内的文件。
    
    参数:
    file_path (str): 要读取的文件路径。
    """
    thread_id = get_thread_id(config)
    workspace_dir = get_workspace_dir(thread_id)
    
    try:
        target_path = validate_and_get_abs_path(workspace_dir, file_path)
        
        if not target_path.exists():
            return f"Error: File {file_path} not found in session {thread_id}."
            
        if target_path.is_dir():
            return f"Error: {file_path} is a directory. Use terminal tools to list contents."
            
        with open(target_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error: {str(e)}"
