"""
健康检查路由
"""

from fastapi import APIRouter
import redis

from ..config import settings
from ..schemas.request import HealthResponse
from .. import __version__

router = APIRouter(tags=["健康检查"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    健康检查接口
    
    检查服务状态、Redis 连接和可用 Worker 数量
    """
    # 检查 Redis 连接
    redis_status = "disconnected"
    try:
        r = redis.from_url(settings.redis_url)
        r.ping()
        redis_status = "connected"
    except Exception as e:
        redis_status = f"error: {str(e)}"
    
    # 获取 Worker 数量
    from src.utils import get_optimal_workers
    workers = settings.max_workers or get_optimal_workers()
    
    return HealthResponse(
        status="ok",
        redis=redis_status,
        workers=workers,
        version=__version__
    )


@router.get("/")
async def root():
    """
    根路径
    """
    return {
        "service": "Code2Video API",
        "version": __version__,
        "docs": "/docs",
        "health": "/health"
    }
