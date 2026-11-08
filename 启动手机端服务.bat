@echo off
chcp 65001
echo ========================================================
echo        盲人辅助系统 - 手机导航服务端启动脚本
echo ========================================================
echo.
echo [1/3] 正在获取本机 IP...
echo [1/3] 正在获取本机 IP (请寻找无线局域网适配器/热点的 IPv4 地址)...
ipconfig | findstr "IPv4"
echo.
echo 注意：如果连接的是手机热点，IP通常是 192.168.43.x 或 172.20.10.x
echo请手动记录上面的 IP 地址
set /p IP="请输入您看到的正确IP地址: "
echo.

echo [2/3] 正在配置防火墙规则 (需要管理员权限)...
netsh advfirewall firewall add rule name="BlindAssistPort5000" dir=in action=allow protocol=TCP localport=5000 >nul 2>&1
echo 防火墙规则已尝试添加 (如果失败请手动允许 Python 通过防火墙)
echo.

echo [3/3] 正在启动 Web 服务 (HTTPS 模式)...
echo ========================================================
echo.
echo   请在手机浏览器输入以下地址 (注意是 HTTPS):
echo.
echo     https://%IP%:5000/mobile
echo.
echo   ★ 浏览器会提示"不安全/不受信任"，这是正常的！
echo     请点击"高级" -> "继续访问" 即可
echo.
echo   ★ HTTPS 是必须的，否则手机浏览器不给高精度GPS权限！
echo.
echo ========================================================
.venv\Scripts\python.exe main.py
pause
