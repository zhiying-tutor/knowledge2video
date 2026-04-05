"""
Celery 任务模块
"""

from .celery_app import celery_app
from .video_tasks import generate_video_task

__all__ = ["celery_app", "generate_video_task"]
