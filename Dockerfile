FROM python:3.12-slim AS builder

WORKDIR /app/think-probe

# 复制依赖文件并安装
COPY .python-version pyproject.toml uv.lock ./
RUN pip install uv && uv sync

# 复制应用代码和配置文件
COPY . .

# 设置默认命令
ENTRYPOINT ["uv", "run", "uvicorn"]
CMD ["run:app", "--host", "0.0.0.0", "--port", "8080"]