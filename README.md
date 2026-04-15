# Think-Probe

Think-Probe 是一个基于 LLM 的轻量级自主编程智能体，旨在展示如何构建具有结构化推理、沙箱化工具调用和多智能体协作能力的对话系统。它采用了业界主流智能体（Claude Code、Codex 等）的设计模式，配合现代化 Web 界面，让用户直观地看到 AI 的决策和执行路径。

---

## ✨ 核心特性

### 🧠 智能体架构
- **4-Block Contract Prompt**：系统指令采用 `Identity → Workflow → Tool Use Guidelines → Constraints` 四段式合同结构，与 Prompt 文件化管理，参考 Claude Code 的设计范式。
- **ReAct 循环**：`Observe → Plan → Act → Verify` 标准化工作流，确保每步可验证。
- **通用子任务委派**：参考 Claude Code 的 `sub_task` 模式，支持主代理动态发起专家级子任务，子代理具备独立执行、深度分析和结果汇总能力。
- **任务追踪**：对复杂任务自动维护 `task.md` 进度文件，支持长任务的断点续跑。
- **扩展技能系统 (Skill System)**：支持通过极简 Markdown（`SKILL.md`）定义复杂技能，Agent 可动态发现并查阅执行指南。

### 🛠️ 工具体系
内置多组沙箱化原生工具，遵循 **专用优先** 原则和 `What + When + Why Not` 描述规范：

| 工具 | 职责 |
| :--- | :--- |
| `read_file` | 读取文件内容，支持行号范围 |
| `edit_file` | 精确字符串替换（最安全的代码修改方式） |
| `write_file` | 创建新文件或完全覆盖 |
| `delete_file` | 删除文件或目录 |
| `list_dir` | 浏览目录结构和项目布局 |
| `grep_search` | 文本/正则搜索，快速定位代码 |
| `bash` | 沙箱 Shell 执行，持久 CWD |
| `sub_task` | 专家级子任务委派（动态生成子代理） |
| `get_skill_info` | 获取扩展技能（Skill）的详细操作正文 |
| `search_skills` | 搜索已安装技能和远程 ClawHub 中可安装的技能 |
| `install_skill` | 按 ClawHub slug 从远程安装技能 |
| `update_skill` | 根据 ClawHub 安装记录更新技能 |
| `remove_skill` | 删除已安装技能 |
| `reload_skills` | 重新扫描技能目录 |
| `list_skill_sources` | 查看默认技能目录和远程 ClawHub 来源 |

### 🔒 安全沙箱
- 工具访问范围限制在当前项目根目录内；会话元数据保存在 `.workspace/{session_id}/`
- 路径穿越防护（`..` 禁止、绝对路径校验）
- `bash` 支持在项目根下的默认 `skills/` 目录安装新 skill，并执行 skill 目录中的脚本
- 命令执行超时保护

### 🧩 Skill 管理
- 只保留项目根目录下的默认技能目录：`skills/`
- 默认远程源为 ClawHub：`https://clawhub.ai`
- 模型通过专用工具直接请求 ClawHub API 搜索技能，并从技能页下载 zip 包进行安装；所有安装和更新都落到 `skills/`
- `SKILL.md` 支持 `requires.bins`、`requires.env`、`requires.python_modules` 等元数据，用于判断技能是否可立即执行

### 🌊 实时交互
- **深度思考可视化**：支持展示 LLM 的 `reasoning_content`（思考链），AI 决策过程不再是"黑盒"
- **流式响应**：通过高度优化的 SSE 路由，支持主/子智能体交替流式输出
- **会话持久化**：集成 SQLite 业务数据库。通过历史上下文显式注入机制，实现稳定、可控的多轮对话状态恢复

### 🏗️ 现代化 UI
- 清新简约的响应式界面
- 智能滚动追踪与手动覆写
- 代码高亮与折叠式思考链展示
- 工具调用过程的结构化可视化

---

## 🚀 快速开始

### 1. 环境准备

确保您的系统已安装 Python 3.12+。推荐使用 [uv](https://github.com/astral-sh/uv) 进行包管理。

```bash
# 安装 uv (如果尚未安装)
pip install uv
```

### 2. 初始化项目

```bash
# 同步依赖并创建虚拟环境
uv sync
```

### 3. 配置环境变量

复制 `.env.example`（如果存在）或直接创建 `.env` 文件，并填写必要的信息：

```ini
LLM_API_PATH=https://api.openai.com/v1 # 或您的代理地址
LLM_API_KEY=sk-...
LLM_MODEL_NAME=qwen3.5-35b-a3b # 建议使用 Qwen2.5/3.5, GPT-4o, DeepSeek-V3 等
```

### 4. 运行应用

```bash
# 启动 FastAPI 服务
python run.py
```

服务启动后，在浏览器访问 [http://127.0.0.1:8080](http://127.0.0.1:8080) 即可开始使用。

---

## 🐳 容器化部署

### 使用 Docker Compose (推荐)

创建或修改 `docker-compose.yml`：

```yaml
services:
  think-probe:
    container_name: think-probe
    image: think-probe:latest
    ports:
      - "18080:8080"
    environment:
      - LLM_API_PATH=http://xxx.xxx.xxx.xxx:1234/v1
      - LLM_API_KEY=your_key
      - LLM_MODEL_NAME=qwen/qwen3-32b
    networks:
      - net-think-probe

networks:
  net-think-probe:
    driver: bridge
```

执行启动命令：

```bash
docker-compose up -d
```

### 本地构建镜像

```bash
# 使用 Makefile 进行多平台构建
make linux-amd64
```

---

## 📁 项目结构

```
app/
├── agents/             # 智能体定义
│   ├── prompts/        # 系统 Prompt 文件（.md 格式，文件化管理）
│   │   ├── main_agent.md # 主代理指令：身份、工作流、委派策略
│   │   └── sub_agent.md  # 子代理指令：通用子任务执行标准
│   ├── base.py         # Agent 基类
│   └── main.py         # 主智能体入口（加载指令、绑定工具）
├── core/               # 核心架构
│   ├── graph.py        # LangGraph 状态机与工具注册
│   ├── llm.py          # LLM 配置与自定义模型
│   ├── agent_factory.py # 子智能体动态工厂
│   └── skill_manager.py # 技能加载与查询核心逻辑
├── skills/             # 扩展技能库
├── tools/              # 沙箱化工具集
│   ├── file_editor.py  # 文件读写/编辑/删除
│   ├── search.py       # 目录浏览与文本搜索
│   └── terminal.py     # Shell 命令执行
├── service/            # 业务逻辑层
├── api/                # FastAPI 路由
└── store/              # 数据库持久化
```

---

## 🛠️ 技术栈

- **核心架构**: [LangGraph](https://www.langchain.com/langgraph), [LangChain](https://www.langchain.com/)
- **后端框架**: [FastAPI](https://fastapi.tiangolo.com/)
- **数据库**: SQLite (Checkpoints + 消息持久化)
- **观测性**: [Langfuse](https://langfuse.com/) (全链路追踪)
- **包管理**: [uv](https://github.com/astral-sh/uv)
- **前端**: Vanilla JS (ES6+), CSS3 (Modern Flex/Grid), HTML5
- **协议**: OpenAI API Standard, MCP, SSE
- **部署**: Docker, Docker Compose

---

## 📝 许可证

本项目采用 [MIT](LICENSE) 许可证。
