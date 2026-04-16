from fastapi import APIRouter, HTTPException

from app.core.skill_manager import SkillManager

router = APIRouter(prefix="/api/skills", tags=["Skills"])

skill_manager = SkillManager()


@router.get("")
async def list_skills():
    """获取当前项目已安装的 skills。"""
    skill_manager.load_skills()
    skills = sorted(skill_manager._skills_cache.values(), key=lambda item: item.name.lower())
    return {
        "skills": [
            {
                "name": skill.name,
                "description": skill.description,
                "version": skill.version,
                "tags": skill.tags,
                "dir_name": skill.dir_name,
                "path": skill_manager._relative_to_project(skill.directory),
                "source": skill.source,
                "homepage": skill.homepage,
            }
            for skill in skills
        ]
    }


@router.get("/{skill_name}")
async def get_skill(skill_name: str):
    """获取单个 skill 的完整详情和 SKILL.md 正文。"""
    skill_manager.load_skills()
    skill = skill_manager._skills_cache.get(skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    return {
        "name": skill.name,
        "description": skill.description,
        "version": skill.version,
        "tags": skill.tags,
        "dir_name": skill.dir_name,
        "path": skill_manager._relative_to_project(skill.directory),
        "source": skill.source,
        "homepage": skill.homepage,
        "instructions": skill.instructions,
    }
