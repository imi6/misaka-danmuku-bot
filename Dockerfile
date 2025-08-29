# ==============================
# 阶段1：构建依赖（仅用于安装依赖）
# ==============================
FROM python:3.11-slim AS builder

# 设置工作目录
WORKDIR /app

# 安装系统依赖（用于编译可能的C扩展）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖清单
COPY requirements.txt .

# 使用pip编译依赖并安装到指定目录（便于后续复制）
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt


# ==============================
# 阶段2：最终运行镜像（轻量化）
# ==============================
FROM python:3.11-slim

# 安全配置：创建非root用户运行服务（避免权限过高）
RUN groupadd -r botgroup && useradd -r -g botgroup botuser

# 设置工作目录
WORKDIR /app

# 复制阶段1编译好的依赖
COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .

# 安装依赖（无需再次编译，速度更快）
RUN pip install --no-cache /wheels/* && rm -rf /wheels

# 复制项目代码（仅复制必要文件，减小镜像体积）
COPY bot.py .
COPY config.py .

# 配置环境变量（默认值，可通过docker run或compose覆盖）
ENV PYTHONUNBUFFERED=1 \
    LOG_LEVEL=INFO \
    API_TIMEOUT=10

# 切换到非root用户
USER botuser

# 健康检查：检测机器人进程是否存活（根据实际情况调整）
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe', timeout=5)" || exit 1

# 启动命令（使用exec确保信号能正确传递给Python进程）
CMD ["python", "bot.py"]