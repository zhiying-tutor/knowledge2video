"""
文件处理工具函数
"""

import os
import json
import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from ..config import settings


def calculate_sha256(file_path: str) -> str:
    """
    计算文件的 SHA256 哈希值
    
    Args:
        file_path: 文件路径
        
    Returns:
        SHA256 哈希值（十六进制字符串）
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # 分块读取，避免大文件占用过多内存
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def save_video_with_hash(source_path: str, metadata: Optional[Dict[str, Any]] = None) -> str:
    """
    将视频文件保存到输出目录，使用 SHA256 哈希值作为文件名
    
    Args:
        source_path: 源视频文件路径
        metadata: 视频元信息（可选）
        
    Returns:
        新的文件名（不含路径）
    """
    # 计算哈希值
    file_hash = calculate_sha256(source_path)
    
    # 获取原始文件扩展名
    _, ext = os.path.splitext(source_path)
    if not ext:
        ext = ".mp4"
    
    # 新文件名
    new_filename = f"{file_hash}{ext}"
    new_path = os.path.join(settings.video_dir, new_filename)
    
    # 如果文件已存在（相同内容），直接返回
    if os.path.exists(new_path):
        return new_filename
    
    # 复制文件到目标目录
    shutil.copy2(source_path, new_path)
    
    # 保存元信息
    if metadata:
        save_metadata(file_hash, metadata)
    
    return new_filename


def get_video_path(filename: str) -> Optional[str]:
    """
    获取视频文件的完整路径
    
    Args:
        filename: 文件名
        
    Returns:
        文件完整路径，如果不存在则返回 None
    """
    file_path = os.path.join(settings.video_dir, filename)
    if os.path.exists(file_path):
        return file_path
    return None


def save_metadata(file_hash: str, metadata: Dict[str, Any]) -> str:
    """
    保存视频元信息
    
    Args:
        file_hash: 文件哈希值
        metadata: 元信息字典
        
    Returns:
        元信息文件路径
    """
    # 添加时间戳
    metadata["saved_at"] = datetime.now().isoformat()
    
    # 保存为 JSON 文件
    metadata_path = os.path.join(settings.metadata_dir, f"{file_hash}.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    return metadata_path


def get_metadata(file_hash: str) -> Optional[Dict[str, Any]]:
    """
    获取视频元信息
    
    Args:
        file_hash: 文件哈希值（不含扩展名）
        
    Returns:
        元信息字典，如果不存在则返回 None
    """
    # 如果传入的是完整文件名，提取哈希部分
    if "." in file_hash:
        file_hash = file_hash.rsplit(".", 1)[0]
    
    metadata_path = os.path.join(settings.metadata_dir, f"{file_hash}.json")
    if os.path.exists(metadata_path):
        with open(metadata_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def get_file_size(file_path: str) -> int:
    """
    获取文件大小（字节）
    
    Args:
        file_path: 文件路径
        
    Returns:
        文件大小
    """
    return os.path.getsize(file_path)


def get_video_duration(file_path: str) -> Optional[float]:
    """
    获取视频时长（秒）
    
    Args:
        file_path: 视频文件路径
        
    Returns:
        视频时长，如果无法获取则返回 None
    """
    ffprobe_path = shutil.which("ffprobe")
    if ffprobe_path:
        try:
            result = subprocess.run(
                [
                    ffprobe_path,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=nw=1:nk=1",
                    file_path,
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                output = (result.stdout or "").strip()
                if output:
                    return float(output)
        except Exception:
            pass

    try:
        from moviepy.editor import VideoFileClip
        with VideoFileClip(file_path) as clip:
            return clip.duration
    except Exception:
        return None
