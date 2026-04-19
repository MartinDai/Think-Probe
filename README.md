# Think-Probe

Think-Probe 是一个面向通用任务编排的智能体运行时与工作台。它围绕模型调用、工具执行、技能扩展、多智能体协作和会话持久化构建，当前最成熟的能力集中在工程任务、本地工作区操作和可观察的 Agent 执行流程。

---

## 能力清单

### 已具备能力

- [x] 通用 Agent Loop：采用 `Observe → Plan → Act → Verify` 的结构化执行流程
- [x] 主代理 + 子代理协作：通过 `sub_task` 委派复杂分析与子任务执行
- [x] 文件系统工具：支持读取、写入、编辑、删除、目录浏览和文本搜索
- [x] 联网网页搜索与抓取：通过 Tavily API 搜索网页并抓取正文
- [x] 工作区 Shell 执行：支持在受控工作区内执行终端命令，每个会话使用隔离 workspace，且每次从该 workspace 根目录开始
- [x] 技能系统：支持通过 `SKILL.md` 定义、发现、安装、更新和移除技能
- [x] 技能来源管理：支持本地技能目录与远程技能源的统一管理
- [x] 会话持久化：使用 SQLite 保存消息、工具调用、推理内容和子线程关系
- [x] 上下文压缩与续跑：支持按上下文阈值触发历史压缩，生成滚动执行摘要并在后续轮次自动注入
- [x] 推理与执行可视化：通过 Web UI 展示 reasoning、工具流和子代理事件
- [x] 流式响应：支持 SSE 流式输出主代理与子代理过程
- [x] 任务追踪：支持通过 `task.md` 记录复杂任务的执行进度
- [x] 沙箱边界控制：限制工具访问范围，提供路径校验与超时保护
- [x] 面向工程任务的高成熟度体验：代码修改、问题分析、命令执行和项目内排障已较完整

### 规划支持的能力

- [ ] 长期记忆层：支持用户偏好、目标、环境上下文和跨会话检索
- [ ] 技能学习闭环：从已完成任务中沉淀流程模板或可复用技能
- [ ] 技能版本治理：支持版本、依赖校验、评分、回滚和验收机制
- [ ] 更丰富的通用工具：Browser、HTTP、API 调用、表单自动化等
- [ ] 多执行后端：支持 Docker、SSH、远程工作区等执行环境
- [ ] 更完整的 MCP 集成：将外部工具与上下文源纳入统一能力层
- [ ] CLI 入口：在 Web UI 之外提供命令行工作模式
- [ ] 后台任务与调度：支持定时任务、异步执行和结果通知
- [ ] 多消息入口：支持 IM / Chat 渠道接入
- [ ] 多租户与多 Agent Profile：支持团队共享与角色隔离
- [ ] 评测与回放体系：支持任务评测、失败归因和回放分析
- [ ] 安全治理增强：支持更细粒度的权限审批、技能签名和来源审计

---

## 核心特性

### 智能体架构

- **4-Block Contract Prompt**：系统指令采用 `Identity → Workflow → Tool Use Guidelines → Constraints` 四段式结构，便于维护与演进。
- **LangGraph 驱动**：主代理和子代理都基于状态图组织推理与工具调用。
- **通用子任务委派**：通过 `sub_task` 动态生成专家子代理，复用完整工具集执行复杂任务。
- **任务追踪**：复杂任务可借助 `task.md` 维持可恢复的执行进度。
- **上下文压缩续跑**：按 token 阈值压缩旧消息，沉淀结构化执行摘要，并在后续轮次作为记忆提示注入主代理。
- **技能驱动扩展**：通过极简 `SKILL.md` 把新能力以声明式方式接入主系统。

### 工具与执行

| 工具 | 作用 |
| :--- | :--- |
| `read_file` | 读取文件内容，支持行号范围 |
| `edit_file` | 精确字符串替换 |
| `write_file` | 创建新文件或完全覆盖 |
| `delete_file` | 删除文件或目录 |
| `list_dir` | 浏览目录结构 |
| `grep_search` | 搜索文本或模式 |
| `web_search` | 使用 Tavily 搜索网页，并可选返回正文 |
| `web_fetch` | 使用 Tavily 抓取指定网页正文 |
| `bash` | 在工作区沙箱内执行 Shell 命令；每个会话使用隔离 workspace，且每次从该 workspace 根目录开始，不复用跨轮次 `cd` 状态 |
| `sub_task` | 派生并运行子代理 |
| `get_skill_info` | 读取已安装技能正文 |
| `search_skills` | 搜索本地与 ClawHub 技能 |
| `install_skill` | 从 ClawHub 安装技能 |
| `update_skill` | 更新已安装技能 |
| `remove_skill` | 删除技能 |
| `reload_skills` | 刷新技能缓存 |
| `list_skill_sources` | 查看技能目录与远程源 |

### 安全与状态

- 工具访问默认限制在当前会话的 workspace 根目录
- 具备路径穿越防护、workspace 根目录约束和命令执行超时保护
- SQLite 持久化保存会话、工具调用、推理内容和子线程映射
- SSE 流式输出支持主代理和子代理交替反馈

---

## 快速开始

### 1. 环境准备

确保系统安装 Python 3.12，推荐使用 [uv](https://github.com/astral-sh/uv) 管理依赖。

```bash
pip install uv
```

### 2. 安装依赖

```bash
uv sync
```

### 3. 配置环境变量

基于项目内的 [.env.example](./.env.example) 创建 `.env`：

```bash
cp .env.example .env
```

然后按需修改 `.env` 中的配置项：

- `LLM_API_PATH` / `LLM_API_KEY` / `LLM_MODEL_NAME`
  用于配置主模型服务
- `LLM_COMPACTION_MODEL_NAME`
  可选，用于配置专门的会话压缩模型；未配置时复用 `LLM_MODEL_NAME`
- `MAX_CONTEXT_TOKENS` / `CONTEXT_WARNING_RATIO` / `CONTEXT_COMPACT_RATIO` / `CONTEXT_RECENT_MESSAGE_COUNT`
  可选，用于配置上下文估算阈值、压缩触发比例和压缩后保留的最近消息窗口
- `TAVILY_API_KEY`
  用于启用 `web_search` 和 `web_fetch`
- `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_BASE_URL`
  用于启用 Langfuse tracing；如果暂时不用，可先留空或删除

联网搜索与抓取当前通过 Tavily 提供：

- `web_search`：调用 Tavily Search，可选返回正文
- `web_fetch`：调用 Tavily Extract 抓取指定 URL 正文
- 需要配置 `TAVILY_API_KEY`

观测当前通过 Langfuse 提供：

- 工作流事件和 LangChain 回调会自动上报到 Langfuse
- 如未配置 Langfuse 相关环境变量，通常只会缺少 tracing，不影响基础对话与工具调用

当前实现依赖以下 API / 服务：

- `Tavily Search API`
- `Tavily Extract API`
- LLM API（兼容 OpenAI Chat Completions）
- Langfuse（可选）

### 4. 启动服务

```bash
python run.py
```

启动后访问 [http://127.0.0.1:8080](http://127.0.0.1:8080)。

---

## 容器化部署

### Docker Compose

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
      - LLM_COMPACTION_MODEL_NAME=qwen/qwen3-8b
    networks:
      - net-think-probe

networks:
  net-think-probe:
    driver: bridge
```

```bash
docker-compose up -d
```

### 本地构建镜像

```bash
make linux-amd64
```

---

## 项目结构

```text
app/
├── agents/               # 主代理与子代理定义、Prompt
├── api/                  # FastAPI 路由
├── core/                 # LangGraph、LLM、技能管理、子代理工厂
├── service/              # 工作流与会话服务
├── store/                # SQLite 持久化
├── tools/                # 文件、搜索、终端等本地工具
└── utils/                # SSE 与日志等辅助组件
skills/                   # 已安装技能目录
```

---

## 技术栈

- **核心**: LangGraph, LangChain
- **后端**: FastAPI
- **数据库**: SQLite + SQLAlchemy + aiosqlite
- **观测**: Langfuse
- **协议**: OpenAI API, MCP, SSE
- **前端**: Vanilla JS + HTML + CSS
- **部署**: Docker, Docker Compose

---

## 许可证

本项目采用 [MIT](LICENSE) 许可证。
