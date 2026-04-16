import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.tools.terminal import get_thread_id, get_workspace_dir


def _validate_path(workspace_dir: Path, rel_path: str) -> Path:
    """校验路径安全性并返回绝对路径，仅允许项目工作区内的相对路径"""
    if rel_path.startswith("/") or rel_path.startswith("\\"):
        raise ValueError("Security Error: 不允许使用绝对路径。请使用相对路径。")

    if ".." in rel_path:
        raise ValueError("Security Error: 路径中不允许包含 '..'。")

    target = (workspace_dir / rel_path).resolve()
    if not str(target).startswith(str(workspace_dir.resolve())):
        raise ValueError("Security Error: 禁止访问项目工作区外部路径。")

    return target


def _clip_text(text: str, limit: int) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 3)] + "..."


def _normalize_domains(domains: list[str]) -> list[str]:
    normalized: list[str] = []
    for domain in domains:
        value = domain.strip().lower()
        if not value:
            continue
        if value.startswith("http://") or value.startswith("https://"):
            parsed = urllib.parse.urlparse(value)
            value = parsed.netloc.lower()
        if value.startswith("www."):
            value = value[4:]
        normalized.append(value)
    return list(dict.fromkeys(normalized))


def _parse_json_response(payload: str) -> Any:
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"远程服务未返回合法 JSON：{exc}") from exc


def _http_post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int = 30) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            body = response.read().decode(charset, errors="replace")
            data = _parse_json_response(body)
            if not isinstance(data, dict):
                raise ValueError("远程服务返回了异常响应结构。")
            return data
    except urllib.error.HTTPError as exc:
        charset = exc.headers.get_content_charset() or "utf-8"
        body = exc.read().decode(charset, errors="replace")
        detail = body.strip() or f"HTTP {exc.code}"
        raise ValueError(f"Tavily 请求失败，HTTP {exc.code}: {detail}") from exc


def _get_tavily_api_key() -> str:
    return os.getenv("TAVILY_API_KEY", "").strip()


def _require_tavily_api_key() -> str:
    api_key = _get_tavily_api_key()
    if not api_key:
        raise ValueError("未配置 TAVILY_API_KEY。")
    return api_key


def _tavily_headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_require_tavily_api_key()}",
        "User-Agent": "Think-Probe/0.1",
    }


def _tavily_search(
    query: str,
    max_results: int,
    domains: list[str],
    search_depth: str,
    include_raw_content: bool,
) -> list[dict[str, str]]:
    payload: dict[str, Any] = {
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
        "include_answer": False,
        "include_images": False,
        "include_raw_content": include_raw_content,
    }
    if domains:
        payload["include_domains"] = domains

    data = _http_post_json(
        "https://api.tavily.com/search",
        payload=payload,
        headers=_tavily_headers(),
        timeout=30,
    )

    items = data.get("results") or []
    if not isinstance(items, list):
        raise ValueError("Tavily Search 返回了异常响应结构。")

    results: list[dict[str, str]] = []
    for item in items[:max_results]:
        if not isinstance(item, dict):
            continue
        results.append({
            "title": str(item.get("title") or "").strip(),
            "url": str(item.get("url") or "").strip(),
            "snippet": _clip_text(item.get("content") or "", 300),
            "content": str(item.get("raw_content") or item.get("content") or "").strip(),
        })
    return results


def _tavily_extract(
    urls: list[str],
    *,
    extract_depth: str,
    include_images: bool = False,
) -> list[dict[str, str]]:
    payload = {
        "urls": urls,
        "extract_depth": extract_depth,
        "include_images": include_images,
    }

    data = _http_post_json(
        "https://api.tavily.com/extract",
        payload=payload,
        headers=_tavily_headers(),
        timeout=30,
    )

    items = data.get("results") or []
    if not isinstance(items, list):
        raise ValueError("Tavily Extract 返回了异常响应结构。")

    extracted: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        extracted.append({
            "title": str(item.get("title") or "").strip(),
            "url": str(item.get("url") or "").strip(),
            "content": str(item.get("raw_content") or item.get("content") or "").strip(),
        })
    return extracted


def _format_web_results(
    provider: str,
    query: str,
    results: list[dict[str, str]],
    fetch_content: bool,
    max_content_chars: int,
) -> str:
    if not results:
        return f"未找到与 '{query}' 相关的网页结果。"

    lines = [
        f"Web search provider: {provider}",
        f"Query: {query}",
        f"Results: {len(results)}",
        "",
    ]

    for idx, item in enumerate(results, start=1):
        lines.append(f"{idx}. {item.get('title') or '(untitled)'}")
        lines.append(f"URL: {item.get('url') or '(missing url)'}")
        snippet = item.get("snippet") or ""
        if snippet:
            lines.append(f"Snippet: {snippet}")
        if fetch_content:
            content = _clip_text(item.get("content") or "", max_content_chars)
            if content:
                lines.append(f"Content: {content}")
        lines.append("")

    return "\n".join(lines).rstrip()


def _format_fetch_results(results: list[dict[str, str]], max_content_chars: int) -> str:
    if not results:
        return "未抓取到网页正文。"

    lines = [f"Fetched pages: {len(results)}", ""]
    for idx, item in enumerate(results, start=1):
        lines.append(f"{idx}. {item.get('title') or '(untitled)'}")
        lines.append(f"URL: {item.get('url') or '(missing url)'}")
        content = _clip_text(item.get("content") or "", max_content_chars)
        if content:
            lines.append(f"Content: {content}")
        lines.append("")
    return "\n".join(lines).rstrip()


@tool(description=(
    "列出指定目录的内容（文件和子目录）。"
    "适用于：在操作前了解项目结构和文件布局、确认目标文件是否存在。"
    "不适用于：查看文件内容（用 read_file）、搜索文件中的文本（用 grep_search）。"
))
def list_dir(path: str, config: RunnableConfig) -> str:
    """
    列出项目工作区内指定目录的内容。

    Args:
        path (str): 目录路径。必须使用【相对路径】（相对于当前会话的 workspace 根目录）。禁止以 '/' 开头。使用 "." 表示 workspace 根目录。
    """
    workspace_dir = get_workspace_dir(get_thread_id(config))

    try:
        target = _validate_path(workspace_dir, path)

        if not target.exists():
            return f"Error: 路径 '{path}' 不存在。"

        if not target.is_dir():
            return f"Error: '{path}' 不是一个目录。请使用 read_file 查看文件内容。"

        entries = []
        for item in sorted(target.iterdir()):
            if item.name.startswith('.'):
                continue

            rel = os.path.relpath(item, workspace_dir)
            if item.is_dir():
                child_count = sum(1 for _ in item.iterdir()) if item.exists() else 0
                entries.append(f"  📁 {rel}/ ({child_count} items)")
            else:
                size = item.stat().st_size
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
    在项目工作区内搜索与给定文本模式匹配的内容。

    Args:
        pattern (str): 搜索模式，支持正则表达式（如 'def .*init' 或 'TODO'）。
        path (str): 搜索的起始路径。必须使用【相对路径】（相对于当前会话的 workspace 根目录）。禁止以 '/' 开头。使用 "." 搜索整个工作空间。
        include (str): 可选。文件名过滤 glob（如 '*.py' 仅搜索 Python 文件）。
        ignore_case (bool): 是否忽略大小写匹配，默认 False。
    """
    workspace_dir = get_workspace_dir(get_thread_id(config))

    try:
        target = _validate_path(workspace_dir, path)

        if not target.exists():
            return f"Error: 路径 '{path}' 不存在。"

        cmd = ["grep", "-rnI", "--color=never"]
        if ignore_case:
            cmd.append("-i")
        if include:
            cmd.extend(["--include", include])
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

        output = result.stdout.strip()
        workspace_str = str(workspace_dir)
        output = output.replace(workspace_str + "/", "")

        lines = output.split("\n")
        if len(lines) >= 50:
            output += "\n\n⚠️ 结果已截断（显示前 50 条匹配）。请缩小搜索范围或使用 include 过滤文件类型。"

        return f"搜索 '{pattern}' 的结果 ({len(lines)} matches):\n{output}"

    except subprocess.TimeoutExpired:
        return "Error: 搜索超时 (15s)。请缩小搜索范围。"
    except ValueError as e:
        return str(e)
    except Exception as e:
        return f"Error: {str(e)}"


class WebSearchInput(BaseModel):
    query: str = Field(description="要搜索的关键词或问题。")
    max_results: int = Field(default=5, ge=1, le=10, description="返回结果数量，建议 3-5。")
    fetch_content: bool = Field(default=True, description="是否同时返回网页正文。")
    max_content_chars: int = Field(
        default=2000,
        ge=500,
        le=12000,
        description="每个结果最多保留多少正文字符。",
    )
    search_depth: Literal["basic", "advanced"] = Field(
        default="advanced",
        description="Tavily 搜索深度。",
    )
    domains: list[str] = Field(
        default_factory=list,
        description="可选域名过滤，如 ['docs.python.org', 'fastapi.tiangolo.com']。",
    )


class WebFetchInput(BaseModel):
    url: str = Field(description="要抓取的网页 URL。")
    max_content_chars: int = Field(
        default=4000,
        ge=500,
        le=20000,
        description="返回正文的最大字符数。",
    )
    extract_depth: Literal["basic", "advanced"] = Field(
        default="advanced",
        description="Tavily 提取深度。",
    )


@tool(
    "web_search",
    args_schema=WebSearchInput,
    description=(
        "使用 Tavily 搜索网页，并可选地一并返回网页正文。"
        "适用于：查询最新信息、查找官方文档、收集网页来源。"
        "需要配置环境变量 TAVILY_API_KEY。"
    ),
)
def web_search(
    query: str,
    max_results: int = 5,
    fetch_content: bool = True,
    max_content_chars: int = 2000,
    search_depth: Literal["basic", "advanced"] = "advanced",
    domains: list[str] | None = None,
) -> str:
    """
    使用 Tavily 搜索网页。
    """
    try:
        normalized_domains = _normalize_domains(domains or [])
        results = _tavily_search(
            query=query,
            max_results=max_results,
            domains=normalized_domains,
            search_depth=search_depth,
            include_raw_content=fetch_content,
        )
        return _format_web_results(
            provider="tavily",
            query=query,
            results=results,
            fetch_content=fetch_content,
            max_content_chars=max_content_chars,
        )
    except Exception as e:
        return f"Error: {str(e)}"


@tool(
    "web_fetch",
    args_schema=WebFetchInput,
    description=(
        "使用 Tavily 抓取单个网页正文。"
        "适用于：已知 URL，想获取较干净的页面正文内容。"
        "需要配置环境变量 TAVILY_API_KEY。"
    ),
)
def web_fetch(
    url: str,
    max_content_chars: int = 4000,
    extract_depth: Literal["basic", "advanced"] = "advanced",
) -> str:
    """
    使用 Tavily 抓取单个网页正文。
    """
    try:
        results = _tavily_extract([url], extract_depth=extract_depth)
        return _format_fetch_results(results, max_content_chars=max_content_chars)
    except Exception as e:
        return f"Error: {str(e)}"
