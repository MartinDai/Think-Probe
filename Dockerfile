FROM python:3.12-slim AS builder

WORKDIR /app/think-probe

# 复制依赖文件并安装
COPY pyproject.toml pdm.lock ./
RUN pip install pdm && pdm install --no-editable

# 复制应用代码和配置文件
COPY . .

# 设置默认命令
ENTRYPOINT ["pdm", "run", "uvicorn"]
CMD ["run:app", "--host", "0.0.0.0", "--port", "8080"]