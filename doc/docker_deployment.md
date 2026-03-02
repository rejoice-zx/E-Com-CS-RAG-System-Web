# Docker 化部署进展

> 更新时间: 2026-03-02

## 概述

已完成项目的 Docker 化配置，支持通过 `docker-compose` 一键部署前后端服务。

## 架构

```
用户浏览器 → [:80] Nginx（前端容器）
                ├── 静态文件（Vue3 构建产物）
                └── /api/* → 代理到后端容器 [:8000]
                                └── SQLite + 数据卷
```

## 新增文件

| 文件 | 说明 |
|------|------|
| `docker-compose.yml` | 服务编排（前端 + 后端 + 数据卷） |
| `.env.example` | 环境变量配置模板 |
| `.dockerignore` | 根目录 Docker 忽略规则 |
| `backend/Dockerfile` | 后端镜像（python:3.11-slim + uvicorn） |
| `backend/.dockerignore` | 后端 Docker 忽略规则 |
| `frontend/Dockerfile` | 前端多阶段构建（Node 构建 → Nginx 运行） |
| `frontend/nginx.conf` | Nginx 反向代理 + SPA 路由 + gzip |
| `frontend/.dockerignore` | 前端 Docker 忽略规则 |

## 使用方法

```bash
# 1. 准备配置
cp .env.example .env
#    编辑 .env，修改 JWT_SECRET_KEY 等

# 2. 构建并启动
docker-compose up -d --build

# 3. 访问
#    前端: http://localhost
#    后端 API 文档: http://localhost/docs
#    健康检查: http://localhost/api/health

# 4. 查看日志
docker-compose logs -f

# 5. 停止服务
docker-compose down
```

## 数据持久化

- `backend-data` 卷 → 挂载到容器 `/app/data`（SQLite 数据库 + 向量索引）
- `backend-logs` 卷 → 挂载到容器 `/app/logs`（应用日志）

## 注意事项

1. 生产环境请务必修改 `.env` 中的 `JWT_SECRET_KEY`
2. 默认前端端口 80，后端端口 8000，可通过 `.env` 中 `FRONTEND_PORT` / `BACKEND_PORT` 修改
3. 前端通过 Nginx 将 `/api/*` 请求代理到后端，无需单独配置 CORS
