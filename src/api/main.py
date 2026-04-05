"""
Code2Video API 服务主入口

启动方式:
    uvicorn api.main:app --reload --port 8080

或者直接运行:
    python -m api.main
"""

import sys
import os
from pathlib import Path

# 确保项目根目录在 sys.path 中
current_dir = Path(__file__).resolve().parent
src_dir = current_dir.parent  # code2video/src
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from .config import settings
from .routes import video_router, files_router, health_router
from . import __version__


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    """
    # 启动时执行
    print(f"🚀 Code2Video API v{__version__} 启动中...")
    print(f"📁 视频存储目录: {settings.video_dir}")
    print(f"🔗 Redis URL: {settings.redis_url}")
    print(f"🔑 API Keys 数量: {len(settings.api_keys)}")
    
    # 检查 Redis 连接
    try:
        import redis
        r = redis.from_url(settings.redis_url)
        r.ping()
        print("✅ Redis 连接成功")
        r.close()
    except Exception as e:
        print(f"⚠️ Redis 连接失败: {e}")
        print("   请确保 Redis 服务已启动")
    
    yield
    
    # 关闭时执行
    print("👋 Code2Video API 关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title="Code2Video API",
    description="""
## 知识点转视频 API 服务

将编程知识点自动转换为教学视频的后端服务。

### 主要功能

- **视频生成**: 根据知识点和用户配置生成教学视频
- **流式进度**: 通过 SSE 实时返回生成进度
- **文件下载**: 支持断点续传的视频文件下载

### 认证方式

所有接口（除健康检查外）都需要在请求头中携带 API Key:

```
X-API-Key: your-api-key
```

### 快速开始

1. 调用 `/api/v1/generate-video` 提交视频生成任务
2. 通过 SSE 流接收实时进度
3. 任务完成后，使用返回的文件名调用 `/api/v1/files/{filename}` 下载视频
    """,
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Task-ID"],  # 暴露自定义头
)


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    全局异常处理器
    """
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"服务器内部错误: {str(exc)}",
            "type": type(exc).__name__,
        }
    )


# 注册路由
app.include_router(health_router)
app.include_router(video_router)
app.include_router(files_router)


# 直接运行入口
if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level="info",
    )
