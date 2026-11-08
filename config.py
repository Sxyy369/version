import os

# Base Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
SNAPSHOT_DIR = os.path.join(BASE_DIR, "web", "static", "snapshots")
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

# Device Configuration
CAMERA_ID = 0  # 0 for Default Webcam, 1 for External
# CAMERA_ID = r"E:\盲人辅助系统\test1.mp4"  # Local Test Video

# Model Paths
YOLO_MODEL_PATH = "yolo11n.pt"  # Will automatically download if not present
SEG_MODEL_PATH = "models/blind_path.pt" # Segmentation model for blind path

# Detection Configuration 目标检测配置参数
CONF_THRESHOLD = 0.25 #检测置信度阈值 (Lowered to catch more objects like the car)
IOU_THRESHOLD = 0.45 #交并比阈值

# Warning Configuration
WARNING_AREA_THRESHOLD = 0.30  # 30% of screen area triggers collision warning
TRAFFIC_LIGHT_AREA_THRESHOLD = 0.01 # 1% of screen for traffic lights (since they are far)
WARNING_COOLDOWN = 0.0  # Reduced to 0 to allow TTS-driven pacing (Real-time update)警告冷却时间 （可实时更新警告）

# Performance Configuration
# Performance Configuration
VIDEO_WIDTH_TARGET = 320 # Reduced to 160 for extreme speed (pixelated)
YOLO_INFERENCE_SIZE = 320 # Force model to infer at this size
FRAME_SKIP = 3 # Process every Nth frame (1=process all, 2=process every 2nd, etc.)

# COCO Class IDs relevant to blind assistance
# 0: person, 1: bicycle, 2: car, 3: motorcycle, 5: bus, 7: truck, 9: traffic light
TARGET_CLASSES = [0, 1, 2, 3, 5, 7, 9]

CLASS_NAMES_CN = {
    0: "人",
    1: "自行车",
    2: "汽车",
    3: "摩托车",
    5: "公交车",
    7: "卡车",
    9: "红绿灯",
    # Segmentation Classes
    100: "盲道", 
    101: "斑马线"
}

# Navigation States
NAV_STATE_ONBOARDING = "ONBOARDING"
NAV_STATE_GUIDING = "GUIDING"

# Color Definitions (BGR)
COLOR_SAFE = (0, 255, 0)
COLOR_WARN = (0, 165, 255) # Orange
COLOR_DANGER = (0, 0, 255)

# LLM Configuration (Phase 3)
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = "https://api.siliconflow.cn/v1"
LLM_MODEL_NAME = "Qwen/Qwen3-VL-8B-Instruct" 
# System Prompt for the blind assistant
LLM_SYSTEM_PROMPT = """你是一个视障人士的智能助手。
我会发给你一张当前视角的图片。
请用简短、口语化的中文描述画面中最关键的信息。
重点关注：路况、障碍物、任何文字提示或潜在危险。
回答限制在25个字左右，像朋友在耳边提醒一样，稍微细致一些。
例如：“正前方有台阶，小心拌倒” 或 “前面是十字路口，是绿灯”。
"""

# Navigation & Voice Config
AMAP_API_KEY = os.environ.get("AMAP_API_KEY", "") # 高德地图Web服务Key
VOICE_WAKE_KEY = "v" # Keyboard key to trigger voice input
