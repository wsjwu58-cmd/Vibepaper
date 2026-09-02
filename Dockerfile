# syntax=docker/dockerfile:1
# =============================================================================
# VibePaper 全栈部署镜像（多阶段构建）
#
# 四个构建 target，可通过 --target 单独构建：
#   web        —— 前端（React + Vite 构建，Nginx 托管 + /api 反向代理网关）
#   java       —— Java 微服务（Maven 构建后仅打包运行时 JRE）
#                 构建 arg：SERVICE_NAME（模块名，默认 identity-service）
#   generation —— 生成服务（Python 3.12 + FastAPI + uv）
#   agent      —— Agent 服务（Node.js 22 + Pi Agent Core）
#
# 用法示例：
#   docker build --target web -t vibepaper-web .
#   docker build --target java --build-arg SERVICE_NAME=canvas-service -t vibepaper-canvas .
#   docker compose up -d --build     # 全栈一键部署（见 docker-compose.yml）
# =============================================================================


# -----------------------------------------------------------------------------
# Stage 1: 前端构建
# -----------------------------------------------------------------------------
FROM node:22.19-alpine AS web-builder
WORKDIR /app
RUN corepack enable
# 先装依赖，利用层缓存
COPY vibepaper-web/package.json vibepaper-web/pnpm-lock.yaml vibepaper-web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY vibepaper-web/ ./
RUN pnpm build


# -----------------------------------------------------------------------------
# Stage 2: 前端运行（Nginx）
# -----------------------------------------------------------------------------
FROM nginx:1.27-alpine AS web
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=web-builder /app/dist /usr/share/nginx/html
EXPOSE 80


# -----------------------------------------------------------------------------
# Stage 3: Java 微服务构建（Maven，Aliyun 镜像加速）
# -----------------------------------------------------------------------------
FROM maven:3.9-eclipse-temurin-21 AS java-builder
WORKDIR /build
RUN mkdir -p /root/.m2 && cat > /root/.m2/settings.xml <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0">
    <mirrors>
        <mirror>
            <id>aliyun</id>
            <mirrorOf>*</mirrorOf>
            <url>https://maven.aliyun.com/repository/public/</url>
        </mirror>
    </mirrors>
</settings>
EOF
COPY vibepaper-services/ ./
RUN mvn -B -q install -DskipTests


# -----------------------------------------------------------------------------
# Stage 4: Java 微服务运行时（按 SERVICE_NAME 选择模块）
# -----------------------------------------------------------------------------
FROM eclipse-temurin:21-jre AS java
ARG SERVICE_NAME=identity-service
ARG SERVICE_VERSION=1.0.0-SNAPSHOT
WORKDIR /app
COPY --from=java-builder /build/${SERVICE_NAME}/target/${SERVICE_NAME}-${SERVICE_VERSION}.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75.0", "-jar", "app.jar"]


# -----------------------------------------------------------------------------
# Stage 5: 生成服务（Python 3.12 + FastAPI）
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS generation
ENV PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    VIBEPAPER_STORAGE_DIR=/data/generation
RUN pip install --no-cache-dir uv
WORKDIR /app
# 先装依赖，利用层缓存
COPY generation-service/pyproject.toml generation-service/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY generation-service/ ./
RUN uv sync --frozen --no-dev
RUN mkdir -p /data/generation
VOLUME ["/data/generation"]
EXPOSE 8090
CMD ["uv", "run", "--no-sync", "uvicorn", "src.generation.main:app", "--host", "0.0.0.0", "--port", "8090"]


# -----------------------------------------------------------------------------
# Stage 6: Agent 服务构建（Node.js 22 + Pi Agent Core monorepo）
# -----------------------------------------------------------------------------
FROM node:22.19-alpine AS agent-builder
WORKDIR /pi
# 与 README 本地构建流程一致：整仓安装（ignore-scripts）后仅构建 agent 工作区
COPY pi-main/ ./
RUN npm install --ignore-scripts --no-audit --no-fund
RUN npm run build --workspace=@vibepaper/pi-agent-service


# -----------------------------------------------------------------------------
# Stage 7: Agent 服务运行时
# -----------------------------------------------------------------------------
FROM node:22.19-alpine AS agent
WORKDIR /vibepaper
# 保持与源码一致的目录层级，保证 ../../../skills 等相对路径解析正确
COPY --from=agent-builder /pi/package.json ./pi-main/package.json
COPY --from=agent-builder /pi/node_modules ./pi-main/node_modules
COPY --from=agent-builder /pi/packages/vibepaper-agent-service ./pi-main/packages/vibepaper-agent-service
COPY skills/ ./skills
WORKDIR /vibepaper/pi-main/packages/vibepaper-agent-service
EXPOSE 8091
# 环境变量（数据库/Redis/模型 Key 等）由 docker-compose 注入
CMD ["node", "dist/server.js"]
