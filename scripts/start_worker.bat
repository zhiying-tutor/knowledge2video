@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ==========================================
echo    Code2Video Celery Worker 启动脚本 (uv)
echo ==========================================
echo.

:: 切换到项目根目录（pyproject.toml 所在目录）
cd /d %~dp0..

:: 检查 Redis 是否运行
echo 检查 Redis 连接...
redis-cli ping >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Redis 未运行，请先启动 Redis 服务
    pause
    exit /b 1
)
echo ✅ Redis 连接正常
echo.

echo 启动 Celery Worker...
echo 按 Ctrl+C 停止
echo.

uv run python -m celery -A src.api.tasks.celery_app worker ^
    --loglevel=info ^
    --pool=solo ^
    -Q video_generation

pause
