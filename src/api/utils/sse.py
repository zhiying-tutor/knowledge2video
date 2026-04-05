"""
SSE (Server-Sent Events) 流式输出管理
"""

import json
import asyncio
from typing import AsyncGenerator, Dict, Any, Optional, Callable
from uuid import uuid4
from datetime import datetime

from ..schemas.request import EventType, SSEEvent


class SSEManager:
    """
    SSE 事件管理器
    
    用于管理流式输出的事件生成和发送
    """
    
    def __init__(self):
        self.events = []
        self.is_finished = False
        self.error: Optional[str] = None
    
    def create_task_id(self) -> str:
        """创建新的任务 ID"""
        return str(uuid4())
    
    def emit_running(self, task_id: str, message: str, data: Optional[Dict[str, Any]] = None) -> str:
        """
        发送 running 事件
        
        Args:
            task_id: 任务 ID
            message: 消息内容
            data: 附加数据
            
        Returns:
            SSE 格式字符串
        """
        event = SSEEvent(task_id=task_id, message=message, data=data)
        return event.to_sse(EventType.RUNNING)
    
    def emit_finished(self, task_id: str, message: str, data: Optional[Dict[str, Any]] = None) -> str:
        """
        发送 finished 事件
        
        Args:
            task_id: 任务 ID
            message: 消息内容
            data: 附加数据
            
        Returns:
            SSE 格式字符串
        """
        event = SSEEvent(task_id=task_id, message=message, data=data)
        return event.to_sse(EventType.FINISHED)
    
    def emit_failed(self, task_id: str, message: str, data: Optional[Dict[str, Any]] = None) -> str:
        """
        发送 failed 事件
        
        Args:
            task_id: 任务 ID
            message: 消息内容
            data: 附加数据
            
        Returns:
            SSE 格式字符串
        """
        event = SSEEvent(task_id=task_id, message=message, data=data)
        return event.to_sse(EventType.FAILED)
    
    def emit_result(self, message: str, data: Dict[str, Any]) -> str:
        """
        发送 result 事件（最终结果）
        
        Args:
            message: 消息内容
            data: 结果数据
            
        Returns:
            SSE 格式字符串
        """
        payload = {
            "message": message,
            "data": data
        }
        return f"event: {EventType.RESULT.value}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


class TaskProgressCallback:
    """
    任务进度回调类
    
    用于在视频生成过程中报告进度
    """
    
    def __init__(self, queue: asyncio.Queue):
        """
        初始化回调
        
        Args:
            queue: 异步队列，用于传递事件
        """
        self.queue = queue
        self.sse_manager = SSEManager()
        self.current_task_id: Optional[str] = None
    
    async def on_stage_start(self, stage_name: str, message: str) -> str:
        """
        阶段开始回调
        
        Args:
            stage_name: 阶段名称
            message: 消息
            
        Returns:
            任务 ID
        """
        task_id = self.sse_manager.create_task_id()
        self.current_task_id = task_id
        event = self.sse_manager.emit_running(task_id, message)
        await self.queue.put(event)
        return task_id
    
    async def on_stage_finish(self, task_id: str, message: str, data: Optional[Dict[str, Any]] = None):
        """
        阶段完成回调
        
        Args:
            task_id: 任务 ID
            message: 消息
            data: 附加数据
        """
        event = self.sse_manager.emit_finished(task_id, message, data)
        await self.queue.put(event)
    
    async def on_stage_failed(self, task_id: str, message: str, data: Optional[Dict[str, Any]] = None):
        """
        阶段失败回调
        
        Args:
            task_id: 任务 ID
            message: 消息
            data: 附加数据
        """
        event = self.sse_manager.emit_failed(task_id, message, data)
        await self.queue.put(event)
    
    async def on_result(self, message: str, data: Dict[str, Any]):
        """
        最终结果回调
        
        Args:
            message: 消息
            data: 结果数据
        """
        event = self.sse_manager.emit_result(message, data)
        await self.queue.put(event)
        await self.queue.put(None)  # 发送结束信号


class SyncTaskProgressCallback:
    """
    同步版本的任务进度回调类
    
    用于在同步代码（如 Celery Worker）中报告进度
    """
    
    def __init__(self, redis_client, channel_name: str):
        """
        初始化回调
        
        Args:
            redis_client: Redis 客户端
            channel_name: Redis 频道名称
        """
        self.redis = redis_client
        self.channel = channel_name
        self.sse_manager = SSEManager()
    
    def on_stage_start(self, stage_name: str, message: str) -> str:
        """阶段开始回调"""
        task_id = self.sse_manager.create_task_id()
        event = self.sse_manager.emit_running(task_id, message)
        self.redis.publish(self.channel, event)
        return task_id
    
    def on_stage_finish(self, task_id: str, message: str, data: Optional[Dict[str, Any]] = None):
        """阶段完成回调"""
        event = self.sse_manager.emit_finished(task_id, message, data)
        self.redis.publish(self.channel, event)
    
    def on_stage_failed(self, task_id: str, message: str, data: Optional[Dict[str, Any]] = None):
        """阶段失败回调"""
        event = self.sse_manager.emit_failed(task_id, message, data)
        self.redis.publish(self.channel, event)
    
    def on_result(self, message: str, data: Dict[str, Any]):
        """最终结果回调"""
        event = self.sse_manager.emit_result(message, data)
        self.redis.publish(self.channel, event)
        # 发送结束信号
        self.redis.publish(self.channel, "__END__")
