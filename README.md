# Think-Probe

Think-Probe 是一个基于 LLM 的轻量级自主编程智能体，旨在展示如何构建具有结构化推理、沙箱化工具调用和多智能体协作能力的对话系统。它采用了业界主流智能体（Claude Code、Codex 等）的设计模式，配合现代化 Web 界面，让用户直观地看到 AI 的决策和执行路径。

---

## ✨ 核心特性

### 🧠 智能体架构
- **4-Block Contract Prompt**：系统指令采用 `Identity → Workflow → Tool Use Guidelines → Constraints` 四段式合同结构，与 Prompt 文件化管理，参考 Claude Code 的设计范式。
- **ReAct 循环**：`Observe → Plan → Act → Verify` 标准化工作流，确保每步可验证。
- **多智能体协作**：基于 Agent Registry 的动态子智能体委派机制，支持领域专家（如 Java Expert）的自动调度。
- **任务追踪**：对复杂任务自动维护 `task.md` 进度文件，支持长任务的断点续跑。

### 🛠️ 工具体系
内置 7 个沙箱化原生工具，遵循 **专用优先** 原则和 `What + When + Why Not` 描述规范：

| 工具 | 职责 |
| :--- | :--- |
| `read_file` | 读取文件内容，支持行号范围 |
| `edit_file` | 精确字符串替换（最安全的代码修改方式） |
| `write_file` | 创建新文件或完全覆盖 |
| `delete_file` | 删除文件或目录 |
| `list_dir` | 浏览目录结构和项目布局 |
| `grep_search` | 文本/正则搜索，快速定位代码 |
| `run_terminal_command` | 沙箱 Shell 执行，持久 CWD |

### 🔒 安全沙箱
- 每个会话拥有独立的隔离工作空间（`.workspace/{session_id}/`）
- 路径穿越防护（`..` 禁止、绝对路径校验）
- 命令执行超时保护

### 🌊 实时交互
- **深度思考可视化**：支持展示 LLM 的 `reasoning_content`（思考链），AI 决策过程不再是"黑盒"
- **流式响应**：通过高度优化的 SSE 路由，支持主/子智能体交替流式输出
- **会话持久化**：集成 SQLite + LangGraph Checkpointer，实现跨进程的会话状态恢复

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
│   ├── base.py         # Agent 基类
│   ├── main.py         # 主智能体（加载 Prompt、注册工具）
│   └── java_expert.py  # Java 领域专家子智能体
├── core/               # 核心架构
│   ├── graph.py        # LangGraph 状态机与工具注册
│   ├── llm.py          # LLM 配置与自定义模型
│   └── agent_factory.py # 子智能体动态工厂
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
