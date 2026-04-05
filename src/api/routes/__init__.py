"""
API 路由模块
"""

from .video import router as video_router
from .files import router as files_router
from .health import router as health_router

__all__ = ["video_router", "files_router", "health_router"]
