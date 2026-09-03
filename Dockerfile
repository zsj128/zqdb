# ============================================================
# 阶段 1：构建前端（Node）
# ============================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# 先复制依赖清单，利用 Docker 层缓存
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --registry=https://registry.npmmirror.com

# 复制前端源码并构建
COPY frontend/ ./
RUN npm run build


# ============================================================
# 阶段 2：后端运行时（Python）
# ============================================================
FROM python:3.10-slim

WORKDIR /app

# 系统依赖（chromadb 可能需要）—— 使用阿里云 Debian 镜像加速
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list 2>/dev/null || true; \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 先单独装 CPU 版 torch（项目只用 CPU 做向量嵌入，无需 CUDA/NVIDIA 库）
# CPU 版约 180MB，而默认完整版 526MB + 十几个 NVIDIA 库（2GB+）
# 用 --find-links 从阿里云 pytorch-wheels/cpu 目录找 CPU 版 wheel（国内快）
# 依赖仍走清华源
RUN pip install --no-cache-dir torch \
    --find-links https://mirrors.aliyun.com/pytorch-wheels/cpu \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 再装其余 Python 依赖（torch 已满足，pip 不会再下载完整版）
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

# 嵌入模型：直接打包进镜像（镜像自包含，运行时无需网络下载）
# 模型位于项目根 models/ 目录
COPY models/ ./models/

# 复制后端代码
COPY backend/ ./backend/

# 复制前端构建产物（供 FastAPI serve）
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# 用户数据目录（data 与 chroma_kb）通过 docker-compose 的 volume 挂载（不打包进镜像）
RUN mkdir -p /root/.law_ai

WORKDIR /app/backend

EXPOSE 8000

# 启动后端（serve 前端静态文件 + API）
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
