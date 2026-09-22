FROM python:3.12-slim

WORKDIR /app

# Runtime-only OS packages. Wheels cover Python deps; skip build-essential.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/
COPY scripts/ scripts/
COPY profiles/ profiles/
COPY site/scripts/ site/scripts/
RUN pip install --no-cache-dir ".[prod]"

# 创建必要目录
RUN mkdir -p /app/output /app/site/src/content/blog /root/.ssh

ENV PYTHONUNBUFFERED=1
ENV OUTPUT_DIR=/app/output

EXPOSE 8080

# 云端默认常驻：健康检查 + 周三/周日调度 + 飞书长连接。
# 单次运行仍可通过覆盖 command 执行 scripts/run_pipeline.py。
CMD ["python", "scripts/run_service.py"]
