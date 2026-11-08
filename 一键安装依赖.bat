@echo off
chcp 65001 >nul
echo ========================================================
echo      智能盲人辅助系统 - 一键安装脚本 (Updated V2)
echo ========================================================
echo.

:: 1. 检查 Python 
set PYTHON_CMD=python
%PYTHON_CMD% --version >nul 2>&1
if %errorlevel% neq 0 (
    set PYTHON_CMD=py
    %PYTHON_CMD% --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo [错误] 未检测到 Python！请先安装 Python 3.10 / 3.11 / 3.12
        echo 下载地址: https://www.python.org/downloads/
        echo 安装时务必勾选 "Add Python to PATH" 选项！
        pause
        exit /b 1
    )
)
echo [OK] 检测到 Python 环境:
%PYTHON_CMD% --version

:: 2. 创建虚拟环境
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [1/5] 正在创建虚拟环境 (.venv)...
    %PYTHON_CMD% -m venv .venv
    if %errorlevel% neq 0 (
        echo [错误] 虚拟环境创建失败！请尝试以管理员身份运行此脚本，或者检查 Python 安装。
        pause
        exit /b 1
    )
) else (
    echo [1/5] 虚拟环境已存在，跳过创建。
)

:: 3. 升级 pip
echo.
echo [2/5] 正在更新 pip (配置清华镜像源)...
.venv\Scripts\python.exe -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple --default-timeout=1000 --quiet

:: 4. 安装主依赖
echo.
echo [3/5] 正在安装主要依赖库（可能需要几分钟，请耐心等待）...
.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --default-timeout=1000
if %errorlevel% neq 0 (
    echo.
    echo [警告] 默认镜像安装可能出错，尝试备用镜像 (阿里云)...
    .venv\Scripts\python.exe -m pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple --default-timeout=1000
)

:: 5. 单独处理 PyAudio
echo.
echo [4/5] 正在单独安装语音输入库 PyAudio (如卡住请耐心等待)...
.venv\Scripts\python.exe -m pip install pyaudio -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 预编译版本安装失败，尝试通过 pipwin 安装...
    .venv\Scripts\python.exe -m pip install pipwin -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet
    .venv\Scripts\python.exe -m pipwin install pyaudio
)
if %errorlevel% neq 0 (
    echo [警告] PyAudio 安装依然不成功。您可以稍后尝试手动安装。
) else (
    echo [OK] PyAudio 安装/检查完毕。
)

:: 6. 修复 OpenCV 冲突
echo.
echo [5/5] 正在修复 OpenCV 潜在冲突...
.venv\Scripts\python.exe -m pip uninstall -y opencv-python-headless >nul 2>&1
.venv\Scripts\python.exe -m pip install opencv-python -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet

echo.
echo ========================================================
echo              所有依赖安装或更新流程已完成！
echo ========================================================
echo.
echo   [提示] 已准备就绪！
echo   如果您使用的是硬件设备(如ESP32摄像头)，请进入 src/config.py 
echo   将 CAMERA_ID 修改为硬件摄像头的局域网 IP 地址 (例如 "http://192.168.1.xxx:81/stream")。
echo.
echo   现在可以双击 "启动系统.bat" 运行本系统。
echo   如需开启手机端导航功能，请双击 "启动手机端服务.bat"。
echo.
pause
