from pathlib import Path
from app.agents.base import Agent
from app.tools.terminal import bash
from app.tools.file_editor import write_file, edit_file, delete_file, read_file
from app.tools.search import list_dir, grep_search
from app.core.skill_manager import skill_manager

# 从独立文件加载系统 Prompt
_PROMPT_DIR = Path(__file__).parent / "prompts"

def _load_prompt(filename: str) -> str:
    """从 prompts 目录加载 Prompt 文件"""
    prompt_path = _PROMPT_DIR / filename
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")

def get_main_agent_instructions() -> str:
    """加载并处理主代理指令，注入动态内容"""
    instructions = _load_prompt("main_agent.md")
    skills_menu = skill_manager.get_skills_menu()
    skill_sources = skill_manager.get_skill_sources_summary()
    return (
        instructions
        .replace("{{SKILLS_MENU}}", skills_menu)
        .replace("{{SKILL_SOURCES}}", skill_sources)
    )

main_agent = Agent(
    name="main",
    instructions=get_main_agent_instructions(),
    tools=[
        # 文件操作（按使用频率排序）
        read_file,
        edit_file,
        write_file,
        delete_file,
        # 搜索与浏览
        list_dir,
        grep_search,
        # 系统任务
        bash,
        # 扩展技能
        skill_manager.get_skill_info_tool(),
        skill_manager.get_skill_sources_tool(),
        skill_manager.get_search_skills_tool(),
        skill_manager.get_install_skill_tool(),
        skill_manager.get_update_skill_tool(),
        skill_manager.get_remove_skill_tool(),
        skill_manager.get_reload_skills_tool(),
    ],
    sub_agents=[],  # Sub-agents are wired in workflow_service
)
