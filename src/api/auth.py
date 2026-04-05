"""
API Key 认证模块
"""

from fastapi import Header, HTTPException, status, Depends
from typing import Optional

from .config import settings


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """
    验证 API Key
    
    Args:
        x_api_key: 请求头中的 API Key
        
    Returns:
        验证通过的 API Key
        
    Raises:
        HTTPException: API Key 无效时抛出 401 错误
    """
    if not settings.is_valid_api_key(x_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return x_api_key


async def verify_api_key_optional(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> Optional[str]:
    """
    可选的 API Key 验证（用于某些公开接口）
    
    Args:
        x_api_key: 请求头中的 API Key（可选）
        
    Returns:
        验证通过的 API Key 或 None
    """
    if x_api_key is None:
        return None
    
    if not settings.is_valid_api_key(x_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return x_api_key


# 依赖注入别名
ApiKeyAuth = Depends(verify_api_key)
ApiKeyAuthOptional = Depends(verify_api_key_optional)
