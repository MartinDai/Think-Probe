from pathlib import Path
from typing import Iterable
from app.agents.base import Agent
from app.tools.terminal import bash
from app.tools.file_editor import write_file, read_file, apply_patch
from app.tools.search import list_dir, grep_search, web_search, web_fetch
from app.core.skill_manager import skill_manager
from app.core.prompt_context import build_current_time_context

# 从独立文件加载系统 Prompt
_PROMPT_DIR = Path(__file__).parent / "prompts"

def _load_prompt(filename: str) -> str:
    """从 prompts 目录加载 Prompt 文件"""
    prompt_path = _PROMPT_DIR / filename
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")

def get_main_agent_instructions(mcp_tool_names: Iterable[str] | None = None) -> str:
    """加载并处理主代理指令，注入动态内容"""
    instructions = _load_prompt("main_agent.md")
    skills_menu = skill_manager.get_skills_menu()
    rendered = (
        instructions
        .replace("{{SKILLS_MENU}}", skills_menu)
        + build_current_time_context()
    )
    tool_names = [name for name in (mcp_tool_names or []) if name]
    if tool_names:
        rendered += (
            "\n\n## Enabled MCP Tools\n"
            "以下 MCP 工具已根据后台启用配置自动注入，可直接按名称调用：\n- "
            + "\n- ".join(tool_names)
        )
    return rendered

main_agent = Agent(
    name="main",
    instructions=get_main_agent_instructions(),
    tools=[
        # 文件操作（按使用频率排序）
        read_file,
        apply_patch,
        write_file,
        # 搜索与浏览
        list_dir,
        grep_search,
        web_search,
        web_fetch,
        # 系统任务
        bash,
        # 扩展技能
        skill_manager.get_load_skill_tool(),
    ],
    sub_agents=[],  # Sub-agents are wired in workflow_service
)
