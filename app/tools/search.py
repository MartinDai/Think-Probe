import os
import subprocess
from pathlib import Path
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from app.tools.terminal import get_workspace_dir


def _validate_path(workspace_dir: Path, rel_path: str) -> Path:
    """校验路径安全性并返回绝对路径，仅允许相对路径"""
    if rel_path.startswith("/") or rel_path.startswith("\\"):
        raise ValueError("Security Error: 不允许使用绝对路径。请使用相对路径。")

    if ".." in rel_path:
        raise ValueError("Security Error: 路径中不允许包含 '..'。")

    target = (workspace_dir / rel_path).resolve()
    if not str(target).startswith(str(workspace_dir.resolve())):
        raise ValueError("Security Error: 禁止访问工作空间外部路径。")

    return target


def _get_thread_id(config: RunnableConfig) -> str:
    """从 RunnableConfig 中提取 thread_id"""
    return config.get("configurable", {}).get("thread_id", "default_session")


@tool(description=(
    "列出指定目录的内容（文件和子目录）。"
    "适用于：在操作前了解项目结构和文件布局、确认目标文件是否存在。"
    "不适用于：查看文件内容（用 read_file）、搜索文件中的文本（用 grep_search）。"
))
def list_dir(path: str, config: RunnableConfig) -> str:
    """
    列出工作空间内指定目录的内容。

    Args:
        path (str): 目录路径。必须使用【相对路径】（相对于当前工作目录）。禁止以 '/' 开头。使用 "." 表示当前目录。
    """
    thread_id = _get_thread_id(config)
    workspace_dir = get_workspace_dir(thread_id)

    try:
        target = _validate_path(workspace_dir, path)

        if not target.exists():
            return f"Error: 路径 '{path}' 不存在。"

        if not target.is_dir():
            return f"Error: '{path}' 不是一个目录。请使用 read_file 查看文件内容。"

        entries = []
        for item in sorted(target.iterdir()):
            # 跳过隐藏文件和常见忽略目录
            if item.name.startswith('.'):
                continue

            rel = os.path.relpath(item, workspace_dir)
            if item.is_dir():
                # 递归统计子项数量
                child_count = sum(1 for _ in item.iterdir()) if item.exists() else 0
                entries.append(f"  📁 {rel}/ ({child_count} items)")
            else:
                size = item.stat().st_size
                # 人类可读的文件大小
                if size < 1024:
                    size_str = f"{size}B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f}KB"
                else:
                    size_str = f"{size / (1024 * 1024):.1f}MB"
                entries.append(f"  📄 {rel} ({size_str})")

        if not entries:
            return f"目录 '{path}' 为空。"

        header = f"📂 {path}/ ({len(entries)} items)\n"
        return header + "\n".join(entries)

    except ValueError as e:
        return str(e)
    except Exception as e:
        return f"Error: {str(e)}"


@tool(description=(
    "在工作空间的文件中搜索文本模式（支持正则表达式）。"
    "适用于：定位代码定义、查找配置项、搜索特定字符串，无需逐个打开文件。"
    "不适用于：查看完整文件内容（用 read_file）、浏览目录（用 list_dir）。"
))
def grep_search(
    pattern: str,
    path: str,
    config: RunnableConfig,
    include: str = "",
    ignore_case: bool = False
) -> str:
    """
    在工作空间内搜索与给定文本模式匹配的内容。

    Args:
        pattern (str): 搜索模式，支持正则表达式（如 'def .*init' 或 'TODO'）。
        path (str): 搜索的起始路径。必须使用【相对路径】（相对于当前工作目录）。禁止以 '/' 开头。使用 "." 搜索整个工作空间。
        include (str): 可选。文件名过滤 glob（如 '*.py' 仅搜索 Python 文件）。
        ignore_case (bool): 是否忽略大小写匹配，默认 False。
    """
    thread_id = _get_thread_id(config)
    workspace_dir = get_workspace_dir(thread_id)

    try:
        target = _validate_path(workspace_dir, path)

        if not target.exists():
            return f"Error: 路径 '{path}' 不存在。"

        # 构建 grep 命令
        cmd = ["grep", "-rnI", "--color=never"]

        if ignore_case:
            cmd.append("-i")

        if include:
            cmd.extend(["--include", include])

        # 限制最大匹配数以防输出爆炸
        cmd.extend(["--max-count=50", "-m", "50"])

        cmd.append(pattern)
        cmd.append(str(target))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(workspace_dir)
        )

        if result.returncode == 1:
            return f"未找到匹配 '{pattern}' 的内容。"

        if result.returncode != 0 and result.returncode != 1:
            return f"Error: 搜索失败 —— {result.stderr.strip()}"

        # 格式化输出：将绝对路径转为相对路径
        output = result.stdout.strip()
        workspace_str = str(workspace_dir)
        output = output.replace(workspace_str + "/", "")

        lines = output.split("\n")
        if len(lines) >= 50:
            output += f"\n\n⚠️ 结果已截断（显示前 50 条匹配）。请缩小搜索范围或使用 include 过滤文件类型。"

        return f"搜索 '{pattern}' 的结果 ({len(lines)} matches):\n{output}"

    except subprocess.TimeoutExpired:
        return "Error: 搜索超时 (15s)。请缩小搜索范围。"
    except ValueError as e:
        return str(e)
    except Exception as e:
        return f"Error: {str(e)}"
