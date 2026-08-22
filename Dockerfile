# Deep Research Agent API 镜像
FROM python:3.13-slim

# 构建元信息
LABEL org.opencontainers.image.title="deep-research-agent"
LABEL org.opencontainers.image.description="LangGraph + smolagents 深度研究 Agent FastAPI 服务"

WORKDIR /app

# 环境：不写 .pyc、stdout 不缓冲（日志实时进 docker logs）
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# 先拷依赖文件再装（利用 Docker 层缓存：requirements 不变则复用该层）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 代码（.dockerignore 已排除 .env/.venv/eval_set 等）
COPY . .

# 非 root 运行（容器安全最佳实践）
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/memory \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
