# ============================================================================
# Code2Video Docker 镜像
# 基于 Python 3.11 + Manim 依赖（LaTeX, ffmpeg, cairo, pango, 中文字体）
# ============================================================================

FROM python:3.11-slim AS base

# 避免交互式安装提示
ENV DEBIAN_FRONTEND=noninteractive

# ============================================================================
# 1. 配置国内镜像源（加速下载）
# ============================================================================
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list 2>/dev/null || true

# ============================================================================
# 2. 安装系统依赖（分步安装，提高成功率）
# ============================================================================
# 先更新并安装基础工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libcairo2-dev \
    libpango1.0-dev \
    pkg-config \
    libegl1 \
    libgl1 \
    libgles2 \
    fonts-noto-cjk \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 单独安装 texlive（包较大，单独一层便于缓存和重试）
# 使用重试机制应对网络不稳定
RUN apt-get update && \
    for i in 1 2 3; do \
        apt-get install -y --no-install-recommends --fix-missing \
            texlive-latex-base \
            texlive-latex-extra \
            texlive-fonts-recommended \
        && break || (echo "=== Retry $i ===" && sleep 5 && apt-get update); \
    done && \
    for i in 1 2 3; do \
        apt-get install -y --no-install-recommends --fix-missing \
            texlive-fonts-extra \
        && break || (echo "=== Retry $i ===" && sleep 5 && apt-get update); \
    done && \
    for i in 1 2 3; do \
        apt-get install -y --no-install-recommends --fix-missing \
            texlive-science \
        && break || (echo "=== Retry $i ===" && sleep 5 && apt-get update); \
    done && \
    rm -rf /var/lib/apt/lists/*

# ============================================================================
# 2. 设置工作目录
# ============================================================================
WORKDIR /app

# ============================================================================
# 3. 安装 Python 依赖
# ============================================================================
# 先复制依赖文件，利用 Docker 缓存
COPY pyproject.toml ./

# 安装 pip 和项目依赖（使用国内镜像源，增加超时和重试）
RUN pip install --no-cache-dir --upgrade pip \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    --timeout 120 --retries 5 && \
    pip install --no-cache-dir . \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    --timeout 120 --retries 5

# ============================================================================
# 4. 复制项目代码
# ============================================================================
COPY src/ ./src/
COPY prompts/ ./prompts/

# 确保输出目录存在（运行时会通过 Volume 挂载）
RUN mkdir -p data/outputs/videos data/outputs/metadata src/CASES

# ============================================================================
# 5. 环境变量默认值
# ============================================================================
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    # Redis 默认连接（docker-compose 中会覆盖）
    REDIS_URL=redis://redis:6379/0 \
    CELERY_BROKER_URL=redis://redis:6379/0 \
    CELERY_RESULT_BACKEND=redis://redis:6379/0 \
    # API 配置
    API_HOST=0.0.0.0 \
    API_PORT=8080 \
    # 输出目录
    OUTPUT_DIR=data/outputs \
    VIDEO_DIR=data/outputs/videos \
    METADATA_DIR=data/outputs/metadata

# ============================================================================
# 6. 暴露端口
# ============================================================================
EXPOSE 8080

# ============================================================================
# 7. 默认启动命令（API 服务）
# ============================================================================
CMD ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
