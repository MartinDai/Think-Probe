# Think-Probe

Think-Probe 是一个基于 LLM 的轻量级智能体应用，旨在展示如何构建具有“思考”过程、工具调用和子智能体协作能力的对话系统。它深度集成了模型上下文协议（MCP），并提供了一个简洁、现代的 Web 界面，让用户直观地看到 AI 的决策和执行路径。

---

## ✨ 核心特性

- **🤔 深度思考可视化**：支持展示 LLM 的 `reasoning_content`（思考链），让 AI 的决策过程不再是“黑盒”。
- **🤖 多智能体协作**：采用由 Main Agent（主智能体）统领、子智能体（如 Java 专家）协作的架构。
- **🛠️ 工具与 MCP 支持**：支持 LangChain 工具调用，并可无缝接入 Model Context Protocol (MCP) 数据源。
- **🌊 实时流式响应**：通过 Server-Sent Events (SSE) 实现打字机式的实时输出。
- **📱 现代化 UI**：清新简约的响应式界面，支持会话列表管理、消息记录持久化。
- **🏗️ 模块化架构**：核心逻辑清晰，易于扩展自己的智能体和工具。

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
LLM_MODEL_NAME=gpt-4o # 支持 thinking 模型的名称
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

## 🛠️ 技术栈

- **后端**: [FastAPI](https://fastapi.tiangolo.com/), [LangChain](https://www.langchain.com/)
- **包管理**: [uv](https://github.com/astral-sh/uv)
- **前端**: Vanilla JS, CSS3, HTML5
- **协议**: OpenAI API standard, MCP, SSE
- **部署**: Docker, Docker Compose

---

## 📝 许可证

本项目采用 [MIT](LICENSE) 许可证。
