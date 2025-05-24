# Think-Probe

一个简单的智能体应用，支持调用tools和MCP的能力，更多功能可以参考代码自行实现

Agent框架：[LangGraph](https://github.com/langchain-ai/langgraph)

## 本地开发

安装依赖

```shell
pip install uv
uv sync
```

配置.env文件中的环境变量，运行run.py启动服务，访问[http://127.0.0.1:8080](http://127.0.0.1:8080)页面即可开始聊天

## 构建镜像

### 构建当前系统架构

```shell
make
```

### 构建指定架构

```shell
make linux-amd64
```

## 服务器容器部署运行

### 导出并压缩镜像文件

```shell
docker save think-probe:1.0.0 | gzip > think-probe-1.0.0.tar.gz
```

### 导入镜像

```shell
docker load < think-probe-1.0.0.tar.gz
```

### docker直接运行

```shell
docker run --name think-probe -e LLM_API_PATH=http://192.168.31.26:1234/v1 -p 18080:8080 -d think-probe:1.0.0
```

### docker-compose方式运行

创建docker-compose.yml文件，修改相关环境变量：
```
services:
  think-probe:
    container_name: think-probe
    image: think-probe:1.0.0
    ports:
      - "18080:8080"
    environment:
      - "OPENAI_API_KEY=sk-xxx"
      - "LLM_API_PATH=https://openrouter.ai/api/v1"
      - "LLM_API_KEY=sk-xxx"
      - "LLM_MODEL_NAME=qwen/qwen-2.5-72b-instruct"
    networks:
      - net-think-probe
networks:
  net-think-probe:
    driver: bridge
```

保存后执行

```shell
docker-compose up -d
```
