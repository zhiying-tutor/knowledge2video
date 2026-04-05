"""
文件下载路由
"""

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from fastapi.responses import FileResponse, StreamingResponse

from ..auth import verify_api_key
from ..config import settings
from ..utils.file_utils import get_video_path, get_metadata, get_file_size

router = APIRouter(prefix="/api/v1", tags=["文件下载"])


@router.get("/files/{filename}")
async def download_file(
    filename: str,
    api_key: str = Depends(verify_api_key),
    range: Optional[str] = Header(None)
):
    """
    下载视频文件
    
    支持 Range 请求（断点续传）。
    
    **请求示例**:
    ```
    GET /api/v1/files/a1b2c3d4...sha256.mp4
    Header: X-API-Key: your-key
    Header: Range: bytes=0-1023  (可选，用于断点续传)
    ```
    
    **响应**:
    - 200 OK: 完整文件
    - 206 Partial Content: 部分文件（Range 请求）
    - 404 Not Found: 文件不存在
    """
    # 获取文件路径
    file_path = get_video_path(filename)
    
    if not file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"文件不存在: {filename}"
        )
    
    # 获取文件大小
    file_size = get_file_size(file_path)
    
    # 确定 MIME 类型
    if filename.endswith(".mp4"):
        media_type = "video/mp4"
    elif filename.endswith(".webm"):
        media_type = "video/webm"
    elif filename.endswith(".avi"):
        media_type = "video/x-msvideo"
    else:
        media_type = "application/octet-stream"
    
    # 处理 Range 请求
    if range:
        return await _handle_range_request(file_path, file_size, range, media_type)
    
    # 返回完整文件
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
        }
    )


async def _handle_range_request(
    file_path: str,
    file_size: int,
    range_header: str,
    media_type: str
) -> StreamingResponse:
    """
    处理 Range 请求（断点续传）
    
    Args:
        file_path: 文件路径
        file_size: 文件大小
        range_header: Range 请求头
        media_type: MIME 类型
        
    Returns:
        StreamingResponse
    """
    # 解析 Range 头
    # 格式: bytes=start-end 或 bytes=start-
    try:
        range_spec = range_header.replace("bytes=", "")
        if "-" not in range_spec:
            raise ValueError("Invalid range format")
        
        parts = range_spec.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else file_size - 1
        
        # 验证范围
        if start >= file_size or end >= file_size or start > end:
            raise HTTPException(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                detail="Invalid range",
                headers={"Content-Range": f"bytes */{file_size}"}
            )
        
    except (ValueError, IndexError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Range header"
        )
    
    # 计算内容长度
    content_length = end - start + 1
    
    # 创建文件流生成器
    async def file_stream():
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = content_length
            chunk_size = 8192  # 8KB chunks
            
            while remaining > 0:
                read_size = min(chunk_size, remaining)
                data = f.read(read_size)
                if not data:
                    break
                remaining -= len(data)
                yield data
    
    return StreamingResponse(
        file_stream(),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=media_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(content_length),
        }
    )


@router.get("/files/{filename}/metadata")
async def get_file_metadata(
    filename: str,
    api_key: str = Depends(verify_api_key)
):
    """
    获取视频文件的元信息
    
    返回视频的知识点、生成时间、Token 使用量等信息。
    
    **响应示例**:
    ```json
    {
        "knowledge_point": "二分搜索",
        "language": "Python",
        "duration": 5,
        "token_usage": {...},
        "created_at": "2024-01-01T12:00:00"
    }
    ```
    """
    # 从文件名提取哈希值
    file_hash = filename.rsplit(".", 1)[0] if "." in filename else filename
    
    metadata = get_metadata(file_hash)
    
    if not metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"元信息不存在: {filename}"
        )
    
    return metadata


@router.head("/files/{filename}")
async def head_file(
    filename: str,
    api_key: str = Depends(verify_api_key)
):
    """
    获取文件信息（HEAD 请求）
    
    用于检查文件是否存在和获取文件大小，不返回文件内容。
    """
    file_path = get_video_path(filename)
    
    if not file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"文件不存在: {filename}"
        )
    
    file_size = get_file_size(file_path)
    
    # 确定 MIME 类型
    if filename.endswith(".mp4"):
        media_type = "video/mp4"
    else:
        media_type = "application/octet-stream"
    
    return StreamingResponse(
        iter([]),  # 空内容
        media_type=media_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
        }
    )
