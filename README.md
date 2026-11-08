# 视界无碍 · 智能导盲辅助系统

视界无碍：辅助盲人识别障碍物，更方便出行

面向视障辅助场景的项目原型，包含视觉识别、盲道分割、语音播报、OCR、大模型场景描述、地图导航、手机端与监护端 Web 页面，以及 ESP32 摄像头固件。

## 项目结构

| 路径 | 内容 |
| --- | --- |
| `main.py`、`config.py` | 主程序与运行配置 |
| `src/` | 目标识别、导航、OCR、语音、传感器融合等模块 |
| `web/` | Flask / Socket.IO 服务和页面 |
| `models/` | 盲道、红绿灯、物品识别与手部模型 |
| `esp32_firmware/` | 摄像头固件及烧录说明 |
| `docs/` | 项目说明与相关资料 |
| `requirements.txt` | Python 依赖列表 |

## 获取完整模型

模型文件由 Git LFS 管理。安装 Git 和 Git LFS 后执行：

```bash
git lfs install
git clone https://github.com/Sxyy369/version.git
cd version
git lfs pull
```

GitHub 网页上的 ZIP 下载未必包含真实模型文件，建议使用上述方式克隆。本仓库保留原包中的 `.pt`、`.onnx`、`.task` 模型及示例视频。

## 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:LLM_API_KEY = "填写自己的大模型 API Key"
$env:AMAP_API_KEY = "填写自己的高德 Web 服务 Key"
$env:AMAP_JS_API_KEY = "填写自己的高德 JavaScript API Key"
$env:AMAP_JS_SECURITY_CODE = "填写自己的高德 JavaScript API 安全密钥"
$env:FLASK_SECRET_KEY = "填写本地随机会话密钥"
.\.venv\Scripts\python.exe main.py
```

`.env.example` 列出了配置项，当前程序读取系统环境变量，不会自动加载 `.env` 文件。地图服务和大模型功能需要配置对应服务的有效凭据；摄像头、麦克风和固件网络参数需按自己的设备设置。原有启动脚本和《使用说明.txt》保留供参考。

## 上传范围

仓库保留业务源码、页面、固件、项目资料、模型和示例视频。Python 虚拟环境、缓存、临时语音、本地账户数据库、历史截图及证书私钥不纳入版本管理。数据库表由服务首次启动时创建，原始账户和历史记录需在本地自行保留。

公开版本已将接口密钥改为环境变量，ESP32 Wi-Fi 参数替换为占位值。项目属于辅助系统原型；功能实现与原项目一致，运行效果依赖硬件、模型、网络及接口配置。
