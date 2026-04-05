# Knowledge2Video API 接入文档

> **编程知识点讲解视频自动生成服务** —— 传入编程知识点和用户信息，自动生成 Manim 动画讲解视频。

---

## 📌 基本信息

| 项目 | 值 |
|------|-----|
| **Base URL** | `http://{server}:8080` |
| **协议** | HTTP |
| **数据格式** | JSON |
| **认证方式** | 请求头 `X-API-Key` |
| **API 文档** | `http://{server}:8080/docs`（Swagger UI） |

---

## 🔑 认证

所有 `/api/v1/*` 接口需要在请求头中携带 API Key：

```
X-API-Key: dev-api-key-12345
```

> 生产环境请联系后端获取正式 API Key。

---

## 📋 接口总览

| 接口 | 方法 | 认证 | 说明 |
|------|------|:----:|------|
| `/` | GET | ❌ | 服务信息（根路径） |
| `/health` | GET | ❌ | 健康检查 |
| `/docs` | GET | ❌ | Swagger API 文档 |
| `/api/v1/generate-video` | POST | ✅ | 生成视频（**SSE 流式返回**） |
| `/api/v1/tasks/{task_id}` | GET | ✅ | 查询任务状态 |
| `/api/v1/files/{filename}` | GET | ✅ | 下载视频文件（支持断点续传） |
| `/api/v1/files/{filename}` | HEAD | ✅ | 获取文件信息（不返回内容） |
| `/api/v1/files/{filename}/metadata` | GET | ✅ | 获取视频元信息 |

---

## 🎬 核心接口：生成视频

### `POST /api/v1/generate-video`

提交编程知识点和用户配置，服务端异步生成讲解视频，通过 **SSE（Server-Sent Events）** 流式返回进度和结果。

### 请求格式

**Content-Type**: `application/json`

**请求体字段说明**：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:----:|--------|------|
| `knowledge_point` | string | ✅ | - | 要生成视频的知识点（如"二分搜索"、"快速排序"、"递归"） |
| `age` | int | ❌ | null | 用户年龄（1-120），影响讲解风格 |
| `gender` | string | ❌ | null | 用户性别（"男"/"女"） |
| `language` | string | ❌ | `"Python"` | 编程语言（Python/Java/C++/JavaScript 等） |
| `duration` | int | ❌ | `5` | 视频时长，单位：分钟（1-30） |
| `difficulty` | string | ❌ | `"medium"` | 内容难度：`"simple"` / `"medium"` / `"hard"` |
| `extra_info` | string | ❌ | null | 用户补充信息（自然语言描述，如学习背景、目标等） |
| `use_feedback` | bool | ❌ | `true` | 是否使用 MLLM 反馈优化视频质量 |
| `use_assets` | bool | ❌ | `true` | 是否使用外部素材增强动画 |
| `api_model` | string | ❌ | 服务端配置 | 指定 LLM 模型：`"claude"` / `"gpt-4o"` / `"gpt-41"` / `"gpt-5"` / `"Gemini"` |

### 请求示例

**完整 JSON 请求体**：

```json
{
  "knowledge_point": "二分搜索",
  "age": 20,
  "gender": "男",
  "language": "Python",
  "duration": 5,
  "difficulty": "medium",
  "extra_info": "我是大学生，有一定编程基础，想深入理解算法"
}
```

**curl 命令**（完整请求）：

```bash
curl -N -X POST http://localhost:8080/api/v1/generate-video \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key-12345" \
  -d '{
    "knowledge_point": "二分搜索",
    "age": 20,
    "gender": "男",
    "language": "Python",
    "duration": 5,
    "difficulty": "medium",
    "extra_info": "我是大学生，有一定编程基础，想深入理解算法"
  }'
```

**curl 命令**（最简请求，仅必填字段）：

```bash
curl -N -X POST http://localhost:8080/api/v1/generate-video \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key-12345" \
  -d '{
    "knowledge_point": "冒泡排序"
  }'
```

### SSE 响应格式

响应为 `text/event-stream`，前端需要使用 EventSource 或 fetch + ReadableStream 来处理。

**SSE 事件类型**：

| 事件类型 | 说明 |
|----------|------|
| `running` | 任务进行中（可能有多条） |
| `finished` | 某个子步骤完成 |
| `failed` | 任务失败 |
| `result` | **最终结果**（包含视频文件名） |

**响应流示例**：

```
event: running
data: {"task_id":"uuid-xxx","message":"正在解析用户画像。"}

event: finished
data: {"task_id":"uuid-xxx","message":"用户画像解析成功。"}

event: running
data: {"task_id":"uuid-xxx","message":"正在生成视频大纲..."}

event: finished
data: {"task_id":"uuid-xxx","message":"大纲生成成功。"}

event: running
data: {"task_id":"uuid-xxx","message":"正在生成 Manim 代码..."}

event: running
data: {"task_id":"uuid-xxx","message":"正在渲染视频..."}

event: result
data: {"message":"视频生成成功。","data":{"video_file":"a1b2c3d4e5f6...sha256.mp4"}}
```

**失败响应**：

```
event: failed
data: {"task_id":"uuid-xxx","message":"视频渲染失败: 内存不足"}
```

> **重要**：收到 `result` 或 `failed` 事件后，SSE 连接会自动关闭。`data` 中的 `video_file` 字段是视频文件名，用于后续下载。

### 响应头

| Header | 说明 |
|--------|------|
| `X-Task-ID` | Celery 任务 ID（可用于断线重连后查询状态） |

---

## 🔍 查询任务状态

### `GET /api/v1/tasks/{task_id}`

用于 SSE 断线重连后查询任务的最终状态。`task_id` 从生成视频接口的响应头 `X-Task-ID` 获取。

**请求示例**：

```bash
curl -H "X-API-Key: dev-api-key-12345" \
  http://localhost:8080/api/v1/tasks/{task_id}
```

**响应示例**：

```json
{
  "task_id": "abc123-def456-...",
  "status": "SUCCESS",
  "result": {
    "video_file": "a1b2c3d4e5f6...sha256.mp4"
  },
  "error": null
}
```

**任务状态**：

| 状态 | 说明 |
|------|------|
| `PENDING` | 等待执行 |
| `STARTED` | 正在执行 |
| `SUCCESS` | 执行成功（`result` 字段有值） |
| `FAILURE` | 执行失败（`error` 字段有值） |

---

## 📥 下载视频文件

### `GET /api/v1/files/{filename}`

下载生成的视频文件。`filename` 从生成视频接口的 `result` 事件中获取。

支持 **Range 请求**（断点续传）。

**请求示例**：

```bash
# 下载完整文件
curl -H "X-API-Key: dev-api-key-12345" \
  http://localhost:8080/api/v1/files/a1b2c3...sha256.mp4 \
  -o video.mp4

# 断点续传（Range 请求）
curl -H "X-API-Key: dev-api-key-12345" \
  -H "Range: bytes=0-1048575" \
  http://localhost:8080/api/v1/files/a1b2c3...sha256.mp4 \
  -o video_part.mp4
```

**响应状态码**：

| 状态码 | 说明 |
|--------|------|
| 200 | 完整文件 |
| 206 | 部分内容（Range 请求） |
| 404 | 文件不存在 |
| 416 | Range 范围无效 |

---

## 📄 获取文件信息

### `HEAD /api/v1/files/{filename}`

检查文件是否存在、获取文件大小。不返回文件内容。

```bash
curl -I -H "X-API-Key: dev-api-key-12345" \
  http://localhost:8080/api/v1/files/a1b2c3...sha256.mp4
```

**响应头**：

```
HTTP/1.1 200 OK
Content-Type: video/mp4
Content-Length: 12345678
Accept-Ranges: bytes
```

---

## 📊 获取视频元信息

### `GET /api/v1/files/{filename}/metadata`

获取视频的生成参数、Token 使用量等元信息。

```bash
curl -H "X-API-Key: dev-api-key-12345" \
  http://localhost:8080/api/v1/files/a1b2c3...sha256.mp4/metadata
```

**响应示例**：

```json
{
  "knowledge_point": "二分搜索",
  "language": "Python",
  "duration": 5,
  "token_usage": {
    "prompt_tokens": 10000,
    "completion_tokens": 5000,
    "total_tokens": 15000
  },
  "created_at": "2024-01-01T12:00:00"
}
```

---

## ❤️ 健康检查

### `GET /health`

无需认证。用于监控服务是否正常运行。

```bash
curl http://localhost:8080/health
```

**响应示例**：

```json
{
  "status": "ok",
  "redis": "connected",
  "workers": 4,
  "version": "1.0.0"
}
```

---

## 🖥️ 前端接入指南

### 完整调用流程

```
┌──────────┐                           ┌──────────────┐
│  前端     │                           │  Knowledge2Video  │
│          │   POST /generate-video     │    API       │
│          │ ─────────────────────────> │              │
│          │                           │              │
│          │   SSE: event: running      │              │
│          │ <───────────────────────── │  正在解析...  │
│          │                           │              │
│          │   SSE: event: finished     │              │
│          │ <───────────────────────── │  大纲完成     │
│          │                           │              │
│          │   SSE: event: running      │              │
│          │ <───────────────────────── │  渲染中...    │
│          │                           │              │
│          │   SSE: event: result       │              │
│          │ <───────────────────────── │  视频完成!    │
│          │                           │              │
│          │   GET /files/{filename}    │              │
│          │ ─────────────────────────> │              │
│          │                           │              │
│          │   video/mp4 文件           │              │
│          │ <───────────────────────── │              │
└──────────┘                           └──────────────┘
```

### 断线重连处理

如果 SSE 连接中断，可以通过 `X-Task-ID`（响应头获取）查询任务状态：

```javascript
async function checkTaskStatus(taskId) {
  const response = await fetch(`http://localhost:8080/api/v1/tasks/${taskId}`, {
    headers: { 'X-API-Key': 'dev-api-key-12345' },
  });
  const result = await response.json();
  
  if (result.status === 'SUCCESS') {
    // 任务已完成，直接下载
    downloadVideo(result.result.video_file);
  } else if (result.status === 'FAILURE') {
    console.error('任务失败:', result.error);
  } else {
    // 任务还在执行中，轮询等待
    setTimeout(() => checkTaskStatus(taskId), 5000);
  }
}
```

---

## ⚠️ 注意事项

1. **视频生成耗时较长**：一个 5 分钟的讲解视频通常需要 3-10 分钟生成，请在 UI 上做好进度展示
2. **SSE 连接保活**：服务端会定期发送心跳（`: heartbeat`），前端无需处理
3. **SSE 超时**：连接超过 1 小时未完成会自动断开
4. **文件有效期**：生成的视频文件会保存在服务端，建议前端在用户下载后不再依赖服务端存储
5. **并发限制**：单个 Worker 同一时间只处理 1 个视频生成任务，多个请求会排队

---

## 🔧 后端部署参考

> 以下内容供需要自行部署后端服务的人员参考。

### 前置要求

- Docker 20.10+
- Docker Compose 2.0+
- 至少 4GB 内存（Manim 渲染需要）
- 至少 10GB 磁盘空间（LaTeX 和字体包较大）

### 快速启动

```bash
# 1. 克隆项目
git clone https://github.com/dxy831/code2video.git
cd code2video

# 2. 配置 LLM API 密钥
#    编辑 src/api_config.json，填入你的 API 密钥

# 3. 配置环境变量（可选）
cp .env.example .env
# 编辑 .env 修改配置

# 4. 构建并启动
docker-compose up -d --build

# 5. 验证服务
curl http://localhost:8080/health
```

### LLM API 密钥配置

编辑 `src/api_config.json` 文件，填入你的 API 密钥：

```json
{
  "api_key": "sk-xxxxx",
  "claude": {
    "base_url": "https://api.anthropic.com/v1",
    "api_version": "",
    "model": "claude-opus-4-5-20251101-cc"
  },
  "gpt4o": {
    "base_url": "https://api.openai.com/v1",
    "api_version": "2024-03-01-preview",
    "model": "gpt-4o"
  },
  "gpt-41": {
    "base_url": "https://api.openai.com/v1",
    "api_version": "2024-03-01-preview",
    "model": "gpt-4o"
  },
  "gpt5": {
    "base_url": "https://api.openai.com/v1",
    "api_version": "",
    "model": "gpt-5.4"
  },
  "gemini": {
    "base_url": "https://generativelanguage.googleapis.com/v1",
    "api_version": "",
    "model": "gemini-3.1-pro-preview"
  },
  "iconfinder": {
    "api_key": "YOUR_ICONFINDER_KEY"
  }
}
```

**支持的 LLM 模型**：

| 配置名 | 说明 |
|--------|------|
| `claude` | Claude 模型（默认） |
| `gpt4o` | GPT-4o 模型 |
| `gpt-41` | GPT-4 系列模型 |
| `gpt5` | GPT-5 模型 |
| `gemini` | Google Gemini 模型 |

> **注意**：`src/api_config.json` 会被打包进 Docker 镜像。如果需要在部署后修改密钥而不重新构建镜像，可以取消 `docker-compose.yml` 中的 Volume 挂载注释。

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `API_KEYS` | API 认证密钥（多个用逗号分隔） | `dev-api-key-12345` |
| `DEFAULT_API` | 默认 LLM 模型（claude/gpt4o/gpt-41/gpt5/gemini） | `claude` |
| `API_PORT` | API 服务端口 | `8080` |
| `REDIS_PORT` | Redis 宿主机映射端口 | `6379` |
| `MAX_WORKERS` | 最大并行工作进程数（留空自动检测） | - |
| `DEBUG` | 调试模式 | `false` |

### 架构

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Compose                        │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │     API      │  │    Worker    │  │    Redis     │   │
│  │  (FastAPI)   │  │   (Celery)   │  │   (队列)     │   │
│  │   :8080      │  │              │  │   :6379      │   │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘   │
│         │                 │                              │
│         └────────┬────────┘                              │
│                  │                                       │
│         ┌───────────────┐                               │
│         │  video_data   │  (共享 Volume)                │
│         │  /app/data/   │                               │
│         └───────────────┘                               │
└─────────────────────────────────────────────────────────┘
```

| 服务 | 说明 | 端口 |
|------|------|------|
| **api** | FastAPI 服务，处理 HTTP 请求 | 8080 |
| **worker** | Celery Worker，执行视频生成任务 | - |
| **redis** | 消息队列 + 任务结果存储 | 6379 |

### 运维命令

```bash
# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f          # 全部
docker-compose logs -f api      # 仅 API
docker-compose logs -f worker   # 仅 Worker

# 重启
docker-compose restart

# 停止
docker-compose down

# 清理所有数据（会删除已生成的视频！）
docker-compose down -v

# 更新部署
git pull && docker-compose up -d --build
```

---

## ⚠️ 常见问题

### 1. 镜像构建很慢

首次构建需要下载 LaTeX 包（约 2GB），请耐心等待。后续构建会使用缓存。

### 2. 内存不足

Manim 渲染需要较多内存，建议至少 4GB。如果遇到 OOM，可以：
- 增加服务器内存
- 减少 Worker 并发数（`--concurrency=1`）

### 3. 中文显示乱码

确保 Docker 镜像中安装了 `fonts-noto-cjk` 字体包（Dockerfile 中已包含）。

### 4. LaTeX 渲染失败

检查 Dockerfile 中是否安装了完整的 texlive 包：
- `texlive-latex-base`
- `texlive-latex-extra`
- `texlive-fonts-recommended`
- `texlive-science`

### 5. 视频文件无法下载

检查 `video_data` Volume 是否正确挂载，API 和 Worker 需要共享同一个 Volume。

---

## 📝 生产环境建议

1. **修改 API_KEYS**：使用强密码，不要用默认值
2. **配置 HTTPS**：在前面加 Nginx 反向代理
3. **日志收集**：配置日志输出到文件或日志服务
4. **监控告警**：监控 `/health` 端点
5. **定期清理**：定期清理旧的视频文件
