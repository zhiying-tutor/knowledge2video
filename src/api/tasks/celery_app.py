"""
Celery 应用配置
"""

from celery import Celery

from ..config import settings

# 创建 Celery 应用
celery_app = Celery(
    "code2video",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["src.api.tasks.video_tasks"]
)

# Celery 配置
celery_app.conf.update(
    # 任务序列化
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    
    # 时区
    timezone="Asia/Shanghai",
    enable_utc=True,
    
    # 任务结果过期时间（秒）
    result_expires=86400,  # 24 小时
    
    # 任务确认
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # 并发控制
    worker_prefetch_multiplier=1,
    
    # 任务路由
    task_routes={
        "src.api.tasks.video_tasks.*": {"queue": "video_generation"},
    },
    
    # 任务时间限制
    task_time_limit=3600,  # 1 小时硬限制
    task_soft_time_limit=3000,  # 50 分钟软限制
    
    # 结果后端配置
    result_backend_transport_options={
        "visibility_timeout": 3600,
    },
)

# 定义任务队列
celery_app.conf.task_queues = {
    "video_generation": {
        "exchange": "video_generation",
        "routing_key": "video_generation",
    },
}
