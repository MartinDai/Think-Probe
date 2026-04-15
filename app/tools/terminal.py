import os
import subprocess
import time
from pathlib import Path
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
WORKSPACE_BASE = PROJECT_ROOT / ".workspace"
SANDBOX_ROOT = PROJECT_ROOT

def get_session_dir(thread_id: str) -> Path:
    """获取并确保会话专用的元数据目录存在"""
    path = WORKSPACE_BASE / thread_id
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
    return path

def get_workspace_dir(thread_id: str) -> Path:
    """返回可供工具访问的项目级工作区根目录"""
    get_session_dir(thread_id)
    return SANDBOX_ROOT

def get_state_file(thread_id: str) -> Path:
    """获取会话专用的终端状态文件路径"""
    return get_session_dir(thread_id) / ".terminal_state"

def get_last_cwd(thread_id: str) -> str:
    """读取会话专用的工作目录（相对 sandbox_root 的路径）"""
    state_file = get_state_file(thread_id)
    if not state_file.exists():
        return "."
    try:
        with open(state_file, "r") as f:
            rel_path = f.read().strip()
            return rel_path if rel_path else "."
    except Exception:
        return "."

def save_cwd(thread_id: str, abs_path: Path):
    """验证并保存会话专用的工作目录（相对于 sandbox_root 的路径）"""
    try:
        resolved_path = abs_path.resolve()
        sandbox_resolved = SANDBOX_ROOT.resolve()
        
        # 严格检查新路径是否在项目沙箱内部
        if str(resolved_path).startswith(str(sandbox_resolved)):
            rel_path = os.path.relpath(resolved_path, sandbox_resolved)
            with open(get_state_file(thread_id), "w") as f:
                f.write(rel_path)
            return True
        else:
            # 逃离尝试：重置回项目根目录
            with open(get_state_file(thread_id), "w") as f:
                f.write(".")
            return False
    except Exception:
        return False

@tool(description=(
    "在项目沙箱内执行 Shell 命令。环境具备按会话持久化的 CWD。"
    "适用于：运行构建系统、包管理器(pip/npm)、Git 操作、测试执行、服务启动等没有专用工具的系统任务。"
    "不适用于：读取文件(用 read_file)、搜索代码(用 grep_search)、浏览目录(用 list_dir)、编辑文件(用 edit_file)。"
    "安全规则：严禁使用 '..' 或项目根目录外的绝对路径。"
    "你可以访问项目根下的 `skills/` 目录，并在其中创建 skill、安装文件、执行脚本。"
))
def bash(command: str, config: RunnableConfig) -> str:
    """
    运行 shell 命令。命令会在项目根目录下执行，并为每个会话持久化当前目录。
    
    Args:
        command (str): 完整的 shell 命令字符串 (例如 'ls -R', 'python3 app.py')。
    """
    # 提取会话 ID (thread_id)
    thread_id = config.get("configurable", {}).get("thread_id", "default_session")
    
    # 初始化会话专用空间
    workspace_dir = get_workspace_dir(thread_id)
    
    # --- 安全审计 ---
    if ".." in command:
        return "Error: Path traversal attempts (using '..') are strictly prohibited."
    
    parts = command.split()
    for part in parts:
        if part.startswith("/") and not part.startswith(str(workspace_dir)):
             return f"Error: Access to absolute paths outside the project workspace is prohibited: {part}"

    # --- 准备执行 ---
    start_rel_cwd = get_last_cwd(thread_id)
    actual_cwd = (workspace_dir / start_rel_cwd).resolve()
    
    # 兜底检查实际 cwd 是否安全
    if not str(actual_cwd).startswith(str(workspace_dir.resolve())):
        actual_cwd = workspace_dir.resolve()
        save_cwd(thread_id, actual_cwd)

    # 构建命令：执行命令后获取当前路径
    wrapped_command = f"({command}) && pwd || pwd"
    
    start_time = time.time()
    try:
        result = subprocess.run(
            wrapped_command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=actual_cwd,
            timeout=30
        )
        duration = time.time() - start_time
        
        # 处理结果并提取最后的 pwd 结果
        stdout_lines = result.stdout.strip().split('\n')
        new_path_str = stdout_lines[-1] if stdout_lines else str(actual_cwd)
        cleaned_stdout = "\n".join(stdout_lines[:-1]) if len(stdout_lines) > 1 else ""
        
        # 验证新路径并更新状态
        if not save_cwd(thread_id, Path(new_path_str)):
            return "Error: Session sandbox violation detected. Operation aborted."

        current_rel_path = get_last_cwd(thread_id)
        
        response = [
            f"Status: {'Success' if result.returncode == 0 else 'Failed'}",
            f"Exit Code: {result.returncode}",
            f"Duration: {duration:.2f}s",
            f"Current Path: {current_rel_path}",
            ""
        ]
        
        if cleaned_stdout:
            response.append(f"STDOUT:\n{cleaned_stdout}")
        
        if result.stderr:
            response.append(f"STDERR:\n{result.stderr}")
            
        return "\n".join(response)

    except subprocess.TimeoutExpired:
        return "Error: Execution timeout (30s)."
    except Exception as e:
        return f"System error: {str(e)}"
