import importlib.util
import io
import json
import os
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List

import yaml
from langchain_core.tools import StructuredTool, tool

from app.schemas.skill import (
    InstallSkillInput,
    RemoveSkillInput,
    SearchSkillsInput,
    UpdateSkillInput,
)
from app.tools.terminal import PROJECT_ROOT

DEFAULT_SKILLS_DIR = PROJECT_ROOT / "skills"
CLAWHUB_SITE = "https://clawhub.ai"
CLAWHUB_API_BASE = f"{CLAWHUB_SITE}/api/v1"
INSTALL_RECORD_FILE = ".skill-install.yaml"
HTTP_HEADERS = {
    "User-Agent": "Think-Probe/0.1 (+https://github.com/martindai/Think-Probe)",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
}


@dataclass(frozen=True)
class SkillRoot:
    name: str
    path: Path
    mutable: bool
    description: str


@dataclass
class RequirementStatus:
    ready: bool
    missing_bins: List[str] = field(default_factory=list)
    missing_env: List[str] = field(default_factory=list)
    missing_python_modules: List[str] = field(default_factory=list)

    def format_summary(self) -> str:
        if self.ready:
            return "ready"

        parts: List[str] = []
        if self.missing_bins:
            parts.append(f"missing bins: {', '.join(self.missing_bins)}")
        if self.missing_env:
            parts.append(f"missing env: {', '.join(self.missing_env)}")
        if self.missing_python_modules:
            parts.append(f"missing python modules: {', '.join(self.missing_python_modules)}")
        return "; ".join(parts)


@dataclass
class Skill:
    name: str
    description: str
    instructions: str
    dir_name: str
    root: SkillRoot
    source_file: Path
    version: str = ""
    tags: List[str] = field(default_factory=list)
    source: str = ""
    homepage: str = ""
    requires: Dict[str, List[str]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_markdown(cls, file_path: Path, root: SkillRoot) -> "Skill":
        content = file_path.read_text(encoding="utf-8")
        if not content.startswith("---"):
            raise ValueError(f"Invalid Skill format in {file_path}: Missing frontmatter")

        parts = content.split("---", 2)
        if len(parts) < 3:
            raise ValueError(f"Invalid Skill format in {file_path}: Incomplete frontmatter")

        frontmatter = yaml.safe_load(parts[1]) or {}
        instructions = parts[2].strip()

        name = frontmatter.get("name")
        if not name:
            raise ValueError(f"Invalid Skill format in {file_path}: 'name' is required in frontmatter")

        requires = frontmatter.get("requires") or {}
        if not isinstance(requires, dict):
            raise ValueError(f"Invalid Skill format in {file_path}: 'requires' must be a mapping")

        return cls(
            name=name,
            description=frontmatter.get("description") or f"Execute skill {name}",
            instructions=instructions,
            dir_name=file_path.parent.name,
            root=root,
            source_file=file_path,
            version=str(frontmatter.get("version") or ""),
            tags=[str(tag) for tag in (frontmatter.get("tags") or [])],
            source=str(frontmatter.get("source") or ""),
            homepage=str(frontmatter.get("homepage") or ""),
            requires={
                "bins": [str(item) for item in (requires.get("bins") or [])],
                "env": [str(item) for item in (requires.get("env") or [])],
                "python_modules": [str(item) for item in (requires.get("python_modules") or [])],
            },
            metadata=frontmatter,
        )

    @property
    def directory(self) -> Path:
        return self.source_file.parent


class _AnchorExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.anchors: List[Dict[str, str]] = []
        self._current_href = ""
        self._text_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, str | None]]):
        if tag != "a":
            return
        self._current_href = ""
        self._text_parts = []
        for key, value in attrs:
            if key == "href" and value:
                self._current_href = value
                break

    def handle_data(self, data: str):
        if self._current_href:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str):
        if tag != "a" or not self._current_href:
            return
        self.anchors.append(
            {
                "href": self._current_href,
                "text": " ".join(part.strip() for part in self._text_parts if part.strip()),
            }
        )
        self._current_href = ""
        self._text_parts = []


class SkillManager:
    """
    管理 Skills 的加载、查询、搜索和安装。
    """

    def __init__(self):
        self._skills_cache: Dict[str, Skill] = {}

    def get_skill_roots(self) -> List[SkillRoot]:
        return [
            SkillRoot("default", DEFAULT_SKILLS_DIR, True, "当前项目默认技能目录"),
        ]

    def load_skills(self):
        self._skills_cache = {}

        for root in self.get_skill_roots():
            if not root.path.exists():
                continue

            for skill_dir in sorted(root.path.iterdir()):
                if not skill_dir.is_dir():
                    continue

                skill_file = skill_dir / "SKILL.md"
                if not skill_file.exists():
                    continue

                try:
                    skill = Skill.from_markdown(skill_file, root)
                except Exception as exc:
                    print(f"Skipping skill in {skill_dir}: {exc}")
                    continue

                if skill.name not in self._skills_cache:
                    self._skills_cache[skill.name] = skill

    def reload(self) -> str:
        self.load_skills()
        return f"Reloaded skills. Installed: {len(self._skills_cache)}."

    def _check_requirements(self, requires: Dict[str, List[str]]) -> RequirementStatus:
        status = RequirementStatus(ready=True)

        for item in requires.get("bins", []):
            if shutil.which(item) is None:
                status.ready = False
                status.missing_bins.append(item)

        for item in requires.get("env", []):
            if not os.getenv(item):
                status.ready = False
                status.missing_env.append(item)

        for item in requires.get("python_modules", []):
            if importlib.util.find_spec(item) is None:
                status.ready = False
                status.missing_python_modules.append(item)

        return status

    def _relative_to_project(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
        except ValueError:
            return str(path.resolve())

    def _sanitize_dir_name(self, name: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-._")
        return cleaned or "skill"

    def _http_get_text(self, url: str, timeout: int = 30) -> str:
        request = urllib.request.Request(url, headers=HTTP_HEADERS)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")

    def _http_get_json(self, url: str, timeout: int = 30) -> Any:
        return json.loads(self._http_get_text(url, timeout=timeout))

    def _download_bytes(self, url: str, timeout: int = 120) -> bytes:
        request = urllib.request.Request(url, headers=HTTP_HEADERS)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()

    def _clawhub_search(self, query: str = "") -> Any:
        if query.strip():
            url = f"{CLAWHUB_API_BASE}/search?q={urllib.parse.quote_plus(query.strip())}"
        else:
            url = f"{CLAWHUB_API_BASE}/skills?sort=trending&limit=20"
        return self._http_get_json(url)

    def _normalize_search_items(self, payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("results", "items"):
                items = payload.get(key)
                if isinstance(items, list):
                    return [item for item in items if isinstance(item, dict)]
        return []

    def _skill_page_from_item(self, item: Dict[str, Any]) -> str:
        for key in ("url", "pageUrl", "href"):
            value = item.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value

        slug = str(item.get("slug") or "").strip()
        owner = str(
            item.get("ownerHandle")
            or item.get("owner")
            or item.get("authorHandle")
            or item.get("publisherHandle")
            or ""
        ).strip().lstrip("@")
        if owner and slug:
            return f"{CLAWHUB_SITE}/{owner}/{slug}"
        if slug:
            return f"{CLAWHUB_SITE}/skills/{slug}"
        raise ValueError("ClawHub result did not include a usable page URL or slug.")

    def _resolve_skill_page_url(self, skill_ref: str) -> str:
        if skill_ref.startswith(("http://", "https://")):
            return skill_ref

        if "/" in skill_ref:
            return f"{CLAWHUB_SITE}/{skill_ref.lstrip('/')}"

        items = self._normalize_search_items(self._clawhub_search(skill_ref))
        if not items:
            raise ValueError(f"No ClawHub search results found for '{skill_ref}'.")

        exact = None
        for item in items:
            slug = str(item.get("slug") or "").strip()
            display_name = str(item.get("displayName") or item.get("name") or "").strip()
            if slug == skill_ref or display_name == skill_ref:
                exact = item
                break

        return self._skill_page_from_item(exact or items[0])

    def _extract_download_url(self, page_html: str) -> str:
        parser = _AnchorExtractor()
        parser.feed(page_html)

        for anchor in parser.anchors:
            href = anchor["href"]
            text = anchor["text"].strip().lower()
            if not href:
                continue
            if "download zip" in text:
                return urllib.parse.urljoin(CLAWHUB_SITE, href)

        patterns = [
            r'href="([^"]+)"[^>]*download[^>]*zip',
            r'href="([^"]+convex\.site[^"]+)"',
            r'href="([^"]+/api/[^"]*download[^"]+)"',
            r'(https://[^"\']+convex\.site[^"\']+\.zip)',
        ]
        for pattern in patterns:
            match = re.search(pattern, page_html, re.IGNORECASE)
            if match:
                return urllib.parse.urljoin(CLAWHUB_SITE, match.group(1))

        raise ValueError("Could not find a downloadable skill archive link on the ClawHub skill page.")

    def _detect_skill_dir(self, checkout_dir: Path) -> Path:
        if (checkout_dir / "SKILL.md").exists():
            return checkout_dir

        candidates = sorted(
            path.parent
            for path in checkout_dir.rglob("SKILL.md")
            if "__pycache__" not in path.parts
        )
        if not candidates:
            raise ValueError("No SKILL.md found in downloaded source.")
        if len(candidates) > 1:
            options = ", ".join(str(path.relative_to(checkout_dir)) for path in candidates[:5])
            raise ValueError(f"Multiple SKILL.md files found. Candidates: {options}")
        return candidates[0]

    def _render_skill_metadata(self, skill: Skill) -> str:
        requirement_status = self._check_requirements(skill.requires)
        lines = [
            f"Skill Name: {skill.name}",
            f"Skill Directory: {self._relative_to_project(skill.directory)}",
            f"Skill File: {self._relative_to_project(skill.source_file)}",
            f"Skill Root: {skill.root.name} ({self._relative_to_project(skill.root.path)})",
            "Relative Path Rule: If the skill instructions reference scripts or files with relative paths, "
            "treat them as relative to the skill directory above.",
            f"Requirements: {requirement_status.format_summary()}",
        ]

        if skill.version:
            lines.append(f"Version: {skill.version}")
        if skill.tags:
            lines.append(f"Tags: {', '.join(skill.tags)}")
        if skill.source:
            lines.append(f"Source: {skill.source}")
        if skill.homepage:
            lines.append(f"Homepage: {skill.homepage}")

        record = self._read_install_record(skill)
        if record.get("clawhub_slug"):
            lines.append(f"ClawHub Slug: {record['clawhub_slug']}")
        if record.get("clawhub_page_url"):
            lines.append(f"ClawHub Page: {record['clawhub_page_url']}")

        return "\n".join(lines)

    def _read_install_record(self, skill: Skill) -> Dict[str, Any]:
        path = skill.directory / INSTALL_RECORD_FILE
        if not path.exists():
            return {}
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}

    def _write_install_record(self, target_dir: Path, clawhub_slug: str, clawhub_page_url: str = ""):
        payload = {
            "source": "clawhub",
            "clawhub_slug": clawhub_slug,
            "clawhub_page_url": clawhub_page_url,
            "installed_from": CLAWHUB_SITE,
        }
        (target_dir / INSTALL_RECORD_FILE).write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    def get_skill_info(self, skill_name: str) -> str:
        if not self._skills_cache:
            self.load_skills()

        skill = self._skills_cache.get(skill_name)
        if not skill:
            return f"Error: Skill '{skill_name}' not found."

        return f"{self._render_skill_metadata(skill)}\n\n{skill.instructions}"

    def get_skills_menu(self) -> str:
        self.load_skills()
        if not self._skills_cache:
            return "（当前无可用扩展技能）"

        menu: List[str] = []
        for name, skill in self._skills_cache.items():
            status = self._check_requirements(skill.requires)
            summary = f"* **{name}** (`{self._relative_to_project(skill.directory)}`): {skill.description}"
            if not status.ready:
                summary += f" [not ready: {status.format_summary()}]"
            menu.append(summary)
        return "\n".join(menu)

    def get_skill_sources_summary(self) -> str:
        lines = ["Skill roots:"]
        for root in self.get_skill_roots():
            marker = "writable" if root.mutable else "read-only"
            lines.append(f"- {root.name}: {self._relative_to_project(root.path)} ({marker})")

        lines.append("")
        lines.append("Remote source:")
        lines.append(f"- ClawHub: {CLAWHUB_SITE}")
        lines.append(f"- Search API: {CLAWHUB_API_BASE}/search")
        lines.append(f"- Catalog API: {CLAWHUB_API_BASE}/skills")
        return "\n".join(lines)

    def search_skills(self, query: str = "", include_installed: bool = True) -> str:
        if not self._skills_cache:
            self.load_skills()

        lines: List[str] = []
        normalized_query = query.strip().lower()

        if include_installed:
            installed_matches = []
            for skill in self._skills_cache.values():
                haystack = " ".join([skill.name, skill.description, " ".join(skill.tags)]).lower()
                if normalized_query and normalized_query not in haystack:
                    continue
                status = self._check_requirements(skill.requires)
                installed_matches.append(
                    f"- installed: {skill.name} at `{self._relative_to_project(skill.directory)}` "
                    f"[root={skill.root.name}, status={status.format_summary()}]"
                )

            if installed_matches:
                lines.append("Installed skills:")
                lines.extend(installed_matches)

        if lines:
            lines.append("")
        lines.append("ClawHub results:")

        try:
            items = self._normalize_search_items(self._clawhub_search(query))
        except Exception as exc:
            lines.append(f"Error: remote search failed: {exc}")
            return "\n".join(lines)

        if not items:
            lines.append("(no remote results returned)")
            return "\n".join(lines)

        for item in items[:10]:
            slug = str(item.get("slug") or "-")
            name = str(item.get("displayName") or item.get("name") or slug)
            summary = str(item.get("summary") or item.get("description") or "-").replace("\n", " ").strip()
            try:
                page_url = self._skill_page_from_item(item)
            except Exception:
                page_url = ""
            entry = f"- {slug}: {name}"
            if summary and summary != "-":
                entry += f" — {summary}"
            if page_url:
                entry += f" [{page_url}]"
            lines.append(entry)
        return "\n".join(lines)

    def install_skill(self, skill_ref: str, force: bool = False) -> str:
        DEFAULT_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        workspace_dir = PROJECT_ROOT / ".workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)

        page_url = self._resolve_skill_page_url(skill_ref)
        page_html = self._http_get_text(page_url, timeout=30)
        download_url = self._extract_download_url(page_html)
        temp_dir = Path(tempfile.mkdtemp(prefix="clawhub-skill-", dir=str(workspace_dir)))

        try:
            archive_bytes = self._download_bytes(download_url, timeout=120)
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
                archive.extractall(temp_dir)

            skill_dir = self._detect_skill_dir(temp_dir)
            parsed_skill = Skill.from_markdown(skill_dir / "SKILL.md", self.get_skill_roots()[0])
            slug_hint = skill_ref.rstrip("/").split("/")[-1]
            target_dir_name = self._sanitize_dir_name(parsed_skill.name or slug_hint)
            target_dir = DEFAULT_SKILLS_DIR / target_dir_name

            if target_dir.exists():
                if not force:
                    return (
                        f"Error: Target skill directory already exists: {self._relative_to_project(target_dir)}. "
                        "Use force=true to replace it."
                    )
                shutil.rmtree(target_dir)

            shutil.copytree(skill_dir, target_dir)
            self._write_install_record(target_dir, skill_ref, clawhub_page_url=page_url)
            self.load_skills()
            status = self._check_requirements(parsed_skill.requires)
            return (
                f"Installed skill '{parsed_skill.name}' from ClawHub into `{self._relative_to_project(target_dir)}`. \n"
                f"Requirement status: {status.format_summary()}. \n"
                f"Download URL: {download_url}"
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def update_skill(self, skill_name: str, force: bool = True) -> str:
        if not self._skills_cache:
            self.load_skills()

        skill = self._skills_cache.get(skill_name)
        if not skill:
            return f"Error: Skill '{skill_name}' not found."

        record = self._read_install_record(skill)
        slug = record.get("clawhub_slug")
        if not slug:
            return (
                f"Error: Skill '{skill_name}' has no ClawHub install record. "
                "Only skills installed from ClawHub can be updated automatically."
            )

        return self.install_skill(str(slug), force=force)

    def remove_skill(self, skill_name: str) -> str:
        if not self._skills_cache:
            self.load_skills()

        skill = self._skills_cache.get(skill_name)
        if not skill:
            return f"Error: Skill '{skill_name}' not found."

        if not skill.root.mutable:
            return f"Error: Skill '{skill_name}' is in a read-only root and cannot be removed."

        shutil.rmtree(skill.directory)
        self.load_skills()
        return f"Removed skill '{skill_name}' from `{self._relative_to_project(skill.directory)}`."

    def get_load_skill_tool(self):
        @tool
        def load_skill(skill_name: str) -> str:
            """
            加载指定 Skill 的正文说明和使用约束。
            当某个已安装 skill 与当前任务匹配时，调用此工具读取其完整指南。
            """

            return self.get_skill_info(skill_name)

        return load_skill

    def get_skill_sources_tool(self) -> StructuredTool:
        def list_skill_sources() -> str:
            """列出默认技能目录和远程 ClawHub 来源。"""

            return self.get_skill_sources_summary()

        return StructuredTool.from_function(
            func=list_skill_sources,
            name="list_skill_sources",
            description=(
                "列出默认技能目录 `skills/` 和远程 ClawHub 来源。"
                "当你需要确认系统会从哪里搜索和安装 skill 时调用。"
            ),
        )

    def get_search_skills_tool(self) -> StructuredTool:
        return StructuredTool.from_function(
            func=self.search_skills,
            name="search_skills",
            description=(
                "搜索已安装技能和远程 ClawHub 中可安装的技能。"
                "当你需要自助发现新的 skill、按关键词查找远程能力、或确认某个 skill 是否已安装时调用。"
            ),
            args_schema=SearchSkillsInput,
        )

    def get_install_skill_tool(self) -> StructuredTool:
        return StructuredTool.from_function(
            func=self.install_skill,
            name="install_skill",
            description=(
                "按 ClawHub slug 或技能页 URL 直接从远程安装一个技能。"
                "安装目标固定为项目根目录下的 `skills/`，安装完成后会立即刷新技能缓存。"
            ),
            args_schema=InstallSkillInput,
        )

    def get_update_skill_tool(self) -> StructuredTool:
        return StructuredTool.from_function(
            func=self.update_skill,
            name="update_skill",
            description=(
                "根据 ClawHub 安装记录更新已安装技能。"
                "仅适用于通过 install_skill 从 ClawHub 安装过的技能。"
            ),
            args_schema=UpdateSkillInput,
        )

    def get_remove_skill_tool(self) -> StructuredTool:
        return StructuredTool.from_function(
            func=self.remove_skill,
            name="remove_skill",
            description=(
                "从默认技能目录中移除一个已安装技能。"
                "适用于清理无用或错误安装的技能。"
            ),
            args_schema=RemoveSkillInput,
        )

    def get_reload_skills_tool(self) -> StructuredTool:
        def reload_skills() -> str:
            """刷新技能缓存。"""

            return self.reload()

        return StructuredTool.from_function(
            func=reload_skills,
            name="reload_skills",
            description=(
                "重新扫描默认技能目录。"
                "当你通过 shell 手工安装/修改了 skills，或怀疑菜单还未反映最新状态时调用。"
            ),
        )


skill_manager = SkillManager()
