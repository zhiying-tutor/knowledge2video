@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ==========================================
echo    Code2Video API 服务启动脚本 (uv)
echo ==========================================
echo.

:: 切换到项目根目录（pyproject.toml 所在目录）
cd /d %~dp0..

:: 检查 Redis 是否运行
echo [1/3] 检查 Redis 连接...
redis-cli ping >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Redis 未运行，请先启动 Redis 服务
    echo    Windows: 运行 redis-server 或启动 Memurai 服务
    pause
    exit /b 1
)
echo ✅ Redis 连接正常

echo.
echo [2/3] 启动 Celery Worker...
echo    请在新的终端窗口中运行 start_worker.bat
echo.
echo    按任意键继续启动 API 服务...
pause >nul

echo.
echo [3/3] 启动 FastAPI 服务...
echo.
echo ==========================================
echo    API 文档: http://localhost:8080/docs
echo    健康检查: http://localhost:8080/health
echo ==========================================
echo.

:: 使用 python -m uvicorn 方式启动（避免 Windows 路径问题）
uv run python -m uvicorn src.api.main:app ^
    --host 0.0.0.0 ^
    --port 8080 ^
    --reload

pause
