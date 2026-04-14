import os
import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional
from langchain_core.tools import tool

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
DEFAULT_SKILLS_DIR = PROJECT_ROOT / "skills"

class Skill:
    def __init__(self, name: str, description: str, instructions: str):
        self.name = name
        self.description = description
        self.instructions = instructions

    @classmethod
    def from_markdown(cls, file_path: Path) -> "Skill":
        content = file_path.read_text(encoding="utf-8")
        if not content.startswith("---"):
            raise ValueError(f"Invalid Skill format in {file_path}: Missing frontmatter")
        
        parts = content.split("---", 2)
        if len(parts) < 3:
             raise ValueError(f"Invalid Skill format in {file_path}: Incomplete frontmatter")
        
        frontmatter_str = parts[1]
        instructions = parts[2]
        frontmatter = yaml.safe_load(frontmatter_str)
        
        if not frontmatter or "name" not in frontmatter:
            raise ValueError(f"Invalid Skill format in {file_path}: 'name' is required in frontmatter")
            
        return cls(
            name=frontmatter.get("name"),
            description=frontmatter.get("description") or f"Execute skill {frontmatter.get('name')}",
            instructions=instructions.strip()
        )

class SkillManager:
    """
    管理 Skills 的加载与查询。
    """
    def __init__(self, skills_dir: Optional[Path] = None):
        self.skills_dir = skills_dir or DEFAULT_SKILLS_DIR
        self._skills_cache: Dict[str, Skill] = {}

    def load_skills(self):
        """扫描目录并缓存所有有效 Skill"""
        self._skills_cache = {}
        if not self.skills_dir.exists():
            return
        
        for skill_dir in self.skills_dir.iterdir():
            if skill_dir.is_dir():
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    try:
                        skill = Skill.from_markdown(skill_file)
                        self._skills_cache[skill.name] = skill
                    except Exception as e:
                        print(f"Skipping skill in {skill_dir}: {e}")

    def get_skill_info(self, skill_name: str) -> str:
        """获取特定 Skill 的原始内容"""
        if not self._skills_cache:
            self.load_skills()
            
        skill = self._skills_cache.get(skill_name)
        if not skill:
            return f"Error: Skill '{skill_name}' not found."
        
        return skill.instructions

    def get_skills_menu(self) -> str:
        """生成所有可用 Skill 的摘要列表"""
        self.load_skills()
        if not self._skills_cache:
            return "（当前无可用扩展技能）"
        
        menu = []
        for name, skill in self._skills_cache.items():
            menu.append(f"* **{name}**: {skill.description}")
        return "\n".join(menu)

    def get_skill_info_tool(self):
        """创建统一的查询工具"""
        
        @tool
        def get_skill_info(skill_name: str) -> str:
            """
            获取指定扩展技能（Skill）的详细操作流程和内容。
            当你需要执行系统 Prompt 中列出的特定技能时，请调用此工具查看其正文说明。
            """
            return self.get_skill_info(skill_name)
            
        return get_skill_info

# 全局单例
skill_manager = SkillManager()
