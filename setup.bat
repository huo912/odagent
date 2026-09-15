@echo off
REM ============================================
REM  OmniDev Agent 环境初始化脚本 (Windows)
REM  1. 创建虚拟环境
REM  2. 安装 Python 依赖
REM  3. 安装前端依赖
REM ============================================
setlocal
cd /d "%~dp0"

echo ============================================
echo  OmniDev Agent 环境初始化
echo ============================================

REM 创建虚拟环境
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 创建虚拟环境...
    python -m venv .venv
) else (
    echo [1/3] 虚拟环境已存在，跳过
)

REM 安装 Python 依赖
echo [2/3] 安装 Python 依赖...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -e odagent

REM 安装前端依赖
echo [3/3] 安装前端依赖...
pushd web
call npm install
popd

echo.
echo 初始化完成！请运行 start.bat 启动服务。
pause
endlocal
