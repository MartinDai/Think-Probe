from pydantic import BaseModel, Field


class SearchSkillsInput(BaseModel):
    query: str = Field(default="", description="搜索关键词。为空时列出全部已安装技能和远程 ClawHub 结果。")
    include_installed: bool = Field(default=True, description="是否同时包含已安装技能。")


class InstallSkillInput(BaseModel):
    skill_ref: str = Field(
        description="ClawHub 上的 skill slug。"
    )
    force: bool = Field(default=False, description="若目标目录已存在，是否覆盖安装。")


class UpdateSkillInput(BaseModel):
    skill_name: str = Field(description="要更新的已安装 skill 名称。")
    force: bool = Field(default=True, description="更新时是否允许覆盖原目录。")


class RemoveSkillInput(BaseModel):
    skill_name: str = Field(description="要移除的已安装 skill 名称。")
