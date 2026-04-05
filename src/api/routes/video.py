"""
视频生成路由
"""

import asyncio
from uuid import uuid4
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
import redis.asyncio as aioredis

from ..auth import verify_api_key
from ..config import settings
from ..schemas.request import VideoGenerateRequest, EventType
from ..tasks.video_tasks import generate_video_task

router = APIRouter(prefix="/api/v1", tags=["视频生成"])


async def sse_event_generator(channel_name: str) -> AsyncGenerator[str, None]:
    """
    SSE 事件生成器
    
    从 Redis 订阅频道读取事件并生成 SSE 流
    
    Args:
        channel_name: Redis 频道名称
        
    Yields:
        SSE 格式的事件字符串
    """
    # 创建异步 Redis 客户端
    redis_client = await aioredis.from_url(settings.redis_url)
    pubsub = redis_client.pubsub()
    
    try:
        await pubsub.subscribe(channel_name)
        
        # 设置超时时间（1小时）
        timeout = 3600
        start_time = asyncio.get_event_loop().time()
        
        while True:
            # 检查超时
            if asyncio.get_event_loop().time() - start_time > timeout:
                yield f"event: {EventType.FAILED.value}\ndata: {{\"message\": \"任务超时\"}}\n\n"
                break
            
            # 获取消息（非阻塞，带超时）
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                # 发送心跳保持连接
                yield ": heartbeat\n\n"
                continue
            
            if message is None:
                # 发送心跳保持连接
                yield ": heartbeat\n\n"
                await asyncio.sleep(0.1)
                continue
            
            data = message.get("data")
            if data:
                # 解码消息
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                
                # 检查结束信号
                if data == "__END__":
                    break
                
                # 直接转发 SSE 事件
                yield data
                
                # 如果是 result 事件，结束流
                if "event: result" in data:
                    break
    
    except Exception as e:
        yield f"event: {EventType.FAILED.value}\ndata: {{\"message\": \"流式传输错误: {str(e)}\"}}\n\n"
    
    finally:
        await pubsub.unsubscribe(channel_name)
        await pubsub.close()
        await redis_client.close()


@router.post("/generate-video")
async def generate_video(
    request: VideoGenerateRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    生成教学视频
    
    接收知识点和用户配置，异步生成教学视频，通过 SSE 流式返回进度。
    
    **请求示例**:
    ```json
    {
        "knowledge_point": "二分搜索",
        "age": 20,
        "gender": "男",
        "language": "Python",
        "duration": 5,
        "extra_info": "我是大学生，有一定编程基础"
    }
    ```
    
    **响应格式** (SSE):
    ```
    event: running
    data: {"task_id":"uuid","message":"正在解析用户画像。"}
    
    event: finished
    data: {"task_id":"uuid","message":"用户画像解析成功。"}
    
    event: result
    data: {"message":"视频生成成功。","data":{"video_file":"sha256.mp4"}}
    ```
    """
    # 生成唯一的频道名称
    channel_name = f"video_task_{uuid4().hex}"
    
    # 准备请求数据
    request_data = {
        "knowledge_point": request.knowledge_point,
        "age": request.age,
        "gender": request.gender,
        "language": request.language or settings.default_language,
        "duration": request.duration or settings.default_duration,
        "extra_info": request.extra_info,
        "use_feedback": request.use_feedback,
        "use_assets": request.use_assets,
        "api_model": request.api_model or settings.default_api,
    }
    
    # 提交 Celery 任务
    try:
        task = generate_video_task.delay(request_data, channel_name)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"任务队列不可用: {str(e)}"
        )
    
    # 返回 SSE 流
    return StreamingResponse(
        sse_event_generator(channel_name),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
            "X-Task-ID": task.id,  # 返回 Celery 任务 ID
        }
    )


@router.get("/tasks/{task_id}")
async def get_task_status(
    task_id: str,
    api_key: str = Depends(verify_api_key)
):
    """
    查询任务状态
    
    用于断线重连后查询任务的最终状态。
    
    **注意**: 此接口返回的是 Celery 任务的状态，不是实时进度。
    实时进度请使用 SSE 流。
    """
    from celery.result import AsyncResult
    from ..tasks.celery_app import celery_app
    
    result = AsyncResult(task_id, app=celery_app)
    
    response = {
        "task_id": task_id,
        "status": result.status,
        "result": None,
        "error": None,
    }
    
    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)
    
    return response
