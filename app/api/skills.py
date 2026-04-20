from fastapi import APIRouter, HTTPException, Request

from app.core.skill_manager import CLAWHUB_SITE, SkillManager
from app.schemas.skill import InstallSkillInput, SearchSkillsInput, UpdateSkillInput

router = APIRouter(prefix="/api/skills", tags=["技能"])

skill_manager = SkillManager()


def _serialize_skill(skill):
    requirement_status = skill_manager._check_requirements(skill.requires)
    install_record = skill_manager._read_install_record(skill)
    return {
        "name": skill.name,
        "description": skill.description,
        "version": skill.version,
        "tags": skill.tags,
        "dir_name": skill.dir_name,
        "path": skill_manager._relative_to_project(skill.directory),
        "source": skill.source,
        "homepage": skill.homepage,
        "clawhub_slug": install_record.get("clawhub_slug", ""),
        "requirements": {
            "ready": requirement_status.ready,
            "summary": requirement_status.format_summary(),
            "missing_bins": requirement_status.missing_bins,
            "missing_env": requirement_status.missing_env,
            "missing_python_modules": requirement_status.missing_python_modules,
        },
    }


@router.get("")
async def list_skills():
    """获取当前项目已安装的 skills。"""
    skill_manager.load_skills()
    skills = sorted(skill_manager._skills_cache.values(), key=lambda item: item.name.lower())
    return {"skills": [_serialize_skill(skill) for skill in skills]}


@router.get("/manage/sources")
async def get_skill_sources():
    """获取 skills 后台管理使用的来源信息。"""
    roots = []
    for root in skill_manager.get_skill_roots():
        roots.append(
            {
                "name": root.name,
                "path": skill_manager._relative_to_project(root.path),
                "mutable": root.mutable,
                "description": root.description,
            }
        )

    return {
        "roots": roots,
        "remote": {
            "name": "ClawHub",
            "site": CLAWHUB_SITE,
        },
        "summary": skill_manager.get_skill_sources_summary(),
    }


@router.post("/manage/reload")
async def reload_skills():
    """刷新 skills 缓存。"""
    message = skill_manager.reload()
    skills = sorted(skill_manager._skills_cache.values(), key=lambda item: item.name.lower())
    return {"status": "success", "message": message, "skills": [_serialize_skill(skill) for skill in skills]}


@router.post("/manage/search")
async def search_skills(request: Request):
    """搜索本地和远程 skills，返回结构化结果供 UI 使用。"""
    data = SearchSkillsInput(**(await request.json()))
    skill_manager.load_skills()

    installed = []
    normalized_query = data.query.strip().lower()
    if data.include_installed:
        for skill in sorted(skill_manager._skills_cache.values(), key=lambda item: item.name.lower()):
            haystack = " ".join([skill.name, skill.description, " ".join(skill.tags)]).lower()
            if normalized_query and normalized_query not in haystack:
                continue
            installed.append(_serialize_skill(skill))

    installed_lookup = {}
    for skill in skill_manager._skills_cache.values():
        serialized = _serialize_skill(skill)
        keys = {
            serialized["name"].strip().lower(),
            serialized["dir_name"].strip().lower(),
            serialized["clawhub_slug"].strip().lower(),
        }
        for key in keys:
            if key:
                installed_lookup[key] = serialized

    remote = []
    remote_error = None
    try:
        items = skill_manager._normalize_search_items(skill_manager._clawhub_search(data.query))
        for item in items[:10]:
            try:
                page_url = skill_manager._skill_page_from_item(item)
            except Exception:
                page_url = ""

            slug = str(item.get("slug") or "").strip()
            name = str(item.get("displayName") or item.get("name") or item.get("slug") or "").strip()
            installed_match = (
                installed_lookup.get(slug.lower())
                or installed_lookup.get(name.lower())
            )

            remote.append(
                {
                    "slug": slug,
                    "name": name,
                    "summary": str(item.get("summary") or item.get("description") or "").replace("\n", " ").strip(),
                    "page_url": page_url,
                    "installed": bool(installed_match),
                    "installed_skill_name": installed_match["name"] if installed_match else "",
                }
            )
    except Exception as exc:
        remote_error = str(exc)

    return {
        "query": data.query,
        "installed": installed,
        "remote": remote,
        "remote_error": remote_error,
    }


@router.post("/manage/install")
async def install_skill(request: Request):
    """安装指定 skill。"""
    payload = InstallSkillInput(**(await request.json()))
    try:
        message = skill_manager.install_skill(payload.skill_ref, force=payload.force)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if message.startswith("Error:"):
        raise HTTPException(status_code=400, detail=message)

    skill_manager.load_skills()
    skills = sorted(skill_manager._skills_cache.values(), key=lambda item: item.name.lower())
    return {"status": "success", "message": message, "skills": [_serialize_skill(skill) for skill in skills]}


@router.post("/manage/update")
async def update_skill(request: Request):
    """更新指定已安装 skill。"""
    payload = UpdateSkillInput(**(await request.json()))
    try:
        message = skill_manager.update_skill(payload.skill_name, force=payload.force)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if message.startswith("Error:"):
        raise HTTPException(status_code=400, detail=message)

    skill_manager.load_skills()
    skills = sorted(skill_manager._skills_cache.values(), key=lambda item: item.name.lower())
    return {"status": "success", "message": message, "skills": [_serialize_skill(skill) for skill in skills]}


@router.delete("/manage/{skill_name}")
async def remove_skill(skill_name: str):
    """移除指定已安装 skill。"""
    try:
        message = skill_manager.remove_skill(skill_name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if message.startswith("Error:"):
        raise HTTPException(status_code=400, detail=message)

    skills = sorted(skill_manager._skills_cache.values(), key=lambda item: item.name.lower())
    return {"status": "success", "message": message, "skills": [_serialize_skill(skill) for skill in skills]}


@router.get("/{skill_name}")
async def get_skill(skill_name: str):
    """获取单个 skill 的完整详情和 SKILL.md 正文。"""
    skill_manager.load_skills()
    skill = skill_manager._skills_cache.get(skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail="没有找到对应的技能")

    return {
        **_serialize_skill(skill),
        "instructions": skill.instructions,
    }
