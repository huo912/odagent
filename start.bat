@echo off
REM ============================================
REM  OmniDev Agent 一键启动脚本 (Windows)
REM  1. 启动 FastAPI 可视化后端 (端口 8000)
REM  2. 启动 Vue3 前端开发服务器 (端口 5173)
REM ============================================
setlocal
cd /d "%~dp0"

echo ============================================
echo  OmniDev Agent 可视化控制台
echo ============================================

REM 检查 venv
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境 .venv，请先运行 setup.bat
    pause
    exit /b 1
)

REM 检查前端依赖
if not exist "web\node_modules" (
    echo [提示] 前端依赖未安装，正在安装...
    pushd web
    call npm install
    popd
)

echo.
echo [1/2] 启动 FastAPI 后端服务 (http://localhost:8000) ...
start "OmniDev-Backend" cmd /k ".venv\Scripts\python.exe -m uvicorn odagent.server:app --host 0.0.0.0 --port 8000"

echo [2/2] 启动 Vue3 前端 (http://localhost:5173) ...
pushd web
call npm run dev
popd

endlocal
