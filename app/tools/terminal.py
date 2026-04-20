import os
import subprocess
import time
from pathlib import Path
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
WORKSPACE_BASE = PROJECT_ROOT / ".workspace"


def get_thread_id(config: RunnableConfig) -> str:
    """从 RunnableConfig 中提取 thread_id"""
    return config.get("configurable", {}).get("thread_id", "default_session")


def get_workspace_dir(thread_id: str) -> Path:
    """返回会话专属的 workspace 根目录，并确保目录存在"""
    workspace_dir = (WORKSPACE_BASE / thread_id).resolve()
    workspace_dir.mkdir(parents=True, exist_ok=True)
    return workspace_dir

@tool(description=(
    "在会话隔离的 workspace 沙箱内执行 Shell 命令。每次都从该会话的 workspace 根目录开始执行，不跨轮次复用 CWD。"
    "适用于：运行构建系统、包管理器(pip/npm)、Git 操作、测试执行、服务启动等没有专用工具的系统任务。"
    "不适用于：读取文件(用 read_file)、搜索代码(用 grep_search)、浏览目录(用 list_dir)、编辑文件(用 apply_patch)。"
    "安全规则：严禁使用 '..' 或当前会话 workspace 根目录外的绝对路径。"
    "如需切换目录，请在单条命令内显式写出完整相对路径。"
))
def bash(command: str, config: RunnableConfig) -> str:
    """
    运行 shell 命令。命令每次都从当前会话的 workspace 根目录下执行，不跨轮次持久化当前目录。
    
    Args:
        command (str): 完整的 shell 命令字符串 (例如 'ls -R', 'python3 app.py')。
    """
    thread_id = get_thread_id(config)
    workspace_dir = get_workspace_dir(thread_id)
    
    # --- 安全审计 ---
    if ".." in command:
        return "Error: Path traversal attempts (using '..') are strictly prohibited."
    
    parts = command.split()
    for part in parts:
        if part.startswith("/") and not part.startswith(str(workspace_dir)):
             return f"Error: Access to absolute paths outside the project workspace is prohibited: {part}"

    actual_cwd = workspace_dir

    # 使用用户当前登录 shell，避免退回到 /bin/sh 丢失 PATH / shell 语义。
    shell_executable = os.environ.get("SHELL") or "/bin/bash"

    # 兼容 macOS / Homebrew 常见环境：系统只有 python3，没有 python 可执行文件。
    wrapped_command = f"""
if ! command -v python >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
    unalias python >/dev/null 2>&1 || true
    eval 'python() {{ python3 "$@"; }}'
fi

({command})
cmd_exit_code=$?
exit $cmd_exit_code
"""
    
    start_time = time.time()
    try:
        result = subprocess.run(
            [shell_executable, "-lc", wrapped_command],
            capture_output=True,
            text=True,
            cwd=actual_cwd,
            timeout=30
        )
        duration = time.time() - start_time
        
        cleaned_stdout = result.stdout.strip()
        
        response = [
            f"Status: {'Success' if result.returncode == 0 else 'Failed'}",
            f"Exit Code: {result.returncode}",
            f"Duration: {duration:.2f}s",
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
