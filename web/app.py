from flask import Flask, render_template, Response, jsonify, request, redirect, url_for
from flask_login import LoginManager, login_required, current_user
from flask_socketio import SocketIO, emit
import threading
import time
import json
import os
import cv2
import base64
from .extensions import db
from .models import User, LogRecord, GuardianSetting
from .auth import auth

app = Flask(__name__)
# In a real app, this should be a random secure key
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)
app.config["AMAP_JS_API_KEY"] = os.environ.get("AMAP_JS_API_KEY", "")
app.config["AMAP_JS_SECURITY_CODE"] = os.environ.get("AMAP_JS_SECURITY_CODE", "")
# Using SQLite for this assignment
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize Extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.init_app(app)

# Initialize SocketIO
# Switch to 'threading' mode to avoid conflict with pyttsx3/pygame/asyncio
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

app.register_blueprint(auth)

# Create tables on startup to ensure DB exists
with app.app_context():
    db.create_all()

from src.map_agent import MapAgent
from src.sensor_fusion import SensorFusion

# Global variables
outputFrame = None
lock = threading.Lock()
# Initialize MapAgent with your Key
AMAP_KEY = os.environ.get("AMAP_API_KEY", "")
map_agent = MapAgent(AMAP_KEY)
# Initialize SensorFusion Engine
sensor_fusion = SensorFusion(step_length=0.6)
# Navigation State
nav_state = {
    "is_navigating": False,
    "destination": None,
    "last_limit_time": 0
}

stats_data = {
    "warnings_count": 0,
    "warning_history": [],
    "current_risks": [],
    "detection_counts": {},
    "logs": [],
    "snapshots": [],
    "status": "Offline",
    "fps": 0,
    "battery": 100,
    "latency": 35,
    "heatmap": [[0]*10 for _ in range(10)]
}

def add_db_log(category, message, user_id=None):
    with app.app_context():
        if user_id is None:
            user = User.query.first()
            if user:
                user_id = user.id
        if user_id:
            record = LogRecord(user_id=user_id, category=category, message=message)
            db.session.add(record)
            db.session.commit()

# Remote Control Queue & Config
remote_speech_queue = []
remote_config = {"sensitivity": 0.3}
current_gps = None

# GPS 平滑滤波器
gps_history = []  # 最近 N 个有效 GPS 点
GPS_HISTORY_SIZE = 3  # 滑动窗口大小
last_valid_gps_time = 0
last_valid_gps_coords = None

def get_latest_config():
    return remote_config

def get_current_gps():
    global current_gps
    return current_gps

def get_map_agent():
    return map_agent

def _haversine_quick(lat1, lon1, lat2, lon2):
    """快速计算两点距离（米）"""
    import math
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2) * math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

@socketio.on('connect')
def handle_connect():
    global last_valid_gps_coords
    if last_valid_gps_coords is not None:
        emit('guardian_gps_update', {
            'lat': last_valid_gps_coords[0],
            'lon': last_valid_gps_coords[1]
        })

@socketio.on('update_gps')
def handle_gps_update(data):
    global current_gps, gps_history, last_valid_gps_time, last_valid_gps_coords
    # data: {lat, lon, acc, spd, head, t}
    
    lat = data.get('lat')
    lon = data.get('lon')
    acc = data.get('acc', 999)
    
    if lat is None or lon is None:
        return
    
    # --- 滤波 1: 精度门槛 (放宽至 5000m 以支持室内及测试) ---
    if acc > 5000:
        print(f"[GPS] 精度过低 (>{acc:.0f}m)，丢弃")
        return
    
    # --- 滤波 2: 速度异常检测 (GPS跳点) ---
    now = time.time()
    if last_valid_gps_coords is not None and last_valid_gps_time > 0:
        dt = now - last_valid_gps_time
        # 如果距离上次有效定位超过 60 秒，认为是全新的会话或者长距离位移，直接放行并更新基准
        if dt > 60:
            last_valid_gps_time = now
            last_valid_gps_coords = (lat, lon)
            gps_history.clear()
        elif dt > 0.5:
            dist = _haversine_quick(last_valid_gps_coords[0], last_valid_gps_coords[1], lat, lon)
            speed_kmh = (dist / dt) * 3.6
            if speed_kmh > 150:
                print(f"[GPS] 速度异常({speed_kmh:.0f}km/h)，疑似跳点，已被丢弃")
                return
    
    # --- 滤波 3: 精度加权滑动窗口平均 ---
    # 我们不仅按时间加权，还按精度加权：精度数值越小(越准)，权重越大
    gps_history.append((lat, lon, acc))
    if len(gps_history) > GPS_HISTORY_SIZE:
        gps_history.pop(0)
    
    if len(gps_history) >= 2:
        total_w = 0
        avg_lat = 0
        avg_lon = 0
        for i, (hlat, hlon, hacc) in enumerate(gps_history):
            # 时间权重 (当前=3, 之前=2, 更早=1)
            time_w = i + 1 
            # 精度权重 (反比：精度值越小，权重越大)
            # 使用 1 / (acc + 1) 作为权重
            acc_w = 100.0 / (hacc + 5.0) 
            
            w = time_w * acc_w
            avg_lat += hlat * w
            avg_lon += hlon * w
            total_w += w
            
        smoothed_lat = avg_lat / total_w
        smoothed_lon = avg_lon / total_w
    else:
        smoothed_lat = lat
        smoothed_lon = lon
    
    # 更新有效 GPS 记录
    last_valid_gps_time = now
    last_valid_gps_coords = (smoothed_lat, smoothed_lon)
    
    # 存储平滑后的结果
    data['lat'] = smoothed_lat
    data['lon'] = smoothed_lon
    current_gps = data
    
    # 向前端所有端推送更新后的坐标，用于实时地图打点
    socketio.emit('guardian_gps_update', {'lat': smoothed_lat, 'lon': smoothed_lon})
    
    # 将平滑后的 GPS 作为绝对定位锚点送入融合引擎
    sensor_fusion.update_gps(smoothed_lat, smoothed_lon, float(acc))
    
    # 获取纠正后的融合坐标进行反向地理编码
    fused_state = sensor_fusion.get_state()
    fused_lat, fused_lon = fused_state['lat'], fused_state['lon']
    address = location_service.get_address_from_gps(fused_lat, fused_lon)
    
    current_gps['address'] = address
    
    # 尝试触发导航播报
    check_navigation_guidance()

@socketio.on('sensor_step')
def handle_sensor_step(data):
    """手机端通过 PDR 传感器发来的一步"""
    heading = data.get('heading', 0)
    sensor_fusion.update_heading(heading)
    
    # 触发融合引擎步进
    success = sensor_fusion.on_step_detected()
    if success:
         check_navigation_guidance(is_step=True, heading=heading)

@socketio.on('guardian_audio')
def handle_guardian_audio(data):
    """
    Receive Base64 audio from guardian dashboard and broadcast to mobile_nav clients.
    """
    print("Received audio from Guardian, broadcasting to blind user...")
    # Send it down to the mobile nav clients
    socketio.emit('play_audio_stream', data)

def check_navigation_guidance(is_step=False, heading=None):
    """
    检查是否需要播报导航。
    无论是 GPS 刷新，还是 PDR 步进，都会调用此方法。
    """
    global nav_state, stats_data
    if not nav_state["is_navigating"]:
        return
        
    now = time.time()
    # 步进时高频更新，限流时间缩短至 2 秒以支持精确倒数
    limit = 2.0 if is_step else 3.0
    
    if now - nav_state["last_limit_time"] > limit:
        loc_str = sensor_fusion.get_fused_location_str()
        if not loc_str:
            return
            
        nav_state["last_limit_time"] = now
        
        # 传入 heading 让 map_agent 能够计算时钟方位 (X 点钟方向)
        guidance = map_agent.get_navigation_guidance(loc_str, heading=heading)
        
        if guidance:
            print(f"[NAV] Guidance Triggered (from {'PDR Step' if is_step else 'GPS'}): {guidance}")
            # 1. Send to Phone to play
            socketio.emit('voice_msg', {'text': guidance})
            
            # 2. Add to backend speech queue
            with lock:
                remote_speech_queue.append({"text": guidance, "sos": False})
                stats_data['logs'].insert(0, {
                    "time": time.strftime("%H:%M:%S"), 
                    "cat": "NAV", 
                    "msg": f"导航指令: {guidance}"
                })
                add_db_log("NAV", f"导航指令: {guidance}")

@socketio.on('request_nav_state')
def handle_request_nav_state():
    global nav_state
    # 每次前端主动请求时，将最新状态单独发给请求者
    emit('nav_state_update', nav_state)
    
@socketio.on('start_nav')
def handle_start_nav(data):
    current_loc = data.get('location', None) # "lon,lat"
    global nav_state, stats_data
    destination = data.get('destination')
    loc_str = data.get('location')  # "lon,lat"
    mode = data.get('mode', 'walking')
    
    if destination and loc_str:
        # 1. Search for POI
        try:
            print(f"[NAV DEBUG] Searching for: {destination}")
            res = map_agent.search_location(destination)
            if res:
                name, target_loc = res
                print(f"[NAV DEBUG] Found {name} at {target_loc}. Planning route from {loc_str} via {mode}...")
                
                # 2. Plan using the selected mode
                msg = map_agent.get_custom_route(loc_str, target_loc, mode=mode)
                
                nav_state["is_navigating"] = True
                nav_state["destination"] = name
                nav_state["mode"] = mode
                
                if msg:
                    full_msg = f"开始导航到{name}。{msg}"
                    socketio.emit('voice_msg', {'text': full_msg})
                    with lock:
                        remote_speech_queue.append({"text": full_msg, "sos": False})
                        stats_data['logs'].insert(0, {"time": time.strftime("%H:%M:%S"), "cat": "NAV", "msg": f"系统播报: {full_msg}"})
                
                add_db_log("NAV_START", f"开始导航到 {name} ({mode})", current_user.id)
                print(f"[NAV] Started navigation to {name}")
            else:
                socketio.emit('voice_msg', {'text': "未找到目的地，请尝试更换关键词。"})
                print(f"[NAV DEBUG] Location not found: {destination}")
        except Exception as e:
            print(f"[NAV ERROR] Failed to start route: {e}")
            socketio.emit('voice_msg', {'text': "导航规划失败，请检查网络或接口配置。"})

@socketio.on('stop_nav')
def handle_stop_nav():
    global nav_state
    if nav_state["is_navigating"]:
        nav_state["is_navigating"] = False
        nav_state["destination"] = None
        add_db_log("NAV_STOP", "已结束导航", current_user.id)
        socketio.emit('voice_msg', {'text': "已结束本次导航。"})
        print("[NAV] Stopped navigation")

frame_count = 0
def update_frame(frame):
    global outputFrame, frame_count
    with lock:
        outputFrame = frame.copy()
    
    # WebSocket Push (Low Latency)
    flag, encodedImage = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
    if flag:
        # Convert to base64 string
        b64_src = "data:image/jpeg;base64," + base64.b64encode(encodedImage).decode('utf-8')
        try:
            socketio.emit('video_frame', {'image': b64_src})
            # Debug log every 30 frames (approx 1 sec)
            frame_count += 1
            if frame_count % 30 == 0:
                # print(f"[WEB] Emitted frame {frame_count}")
                pass
        except Exception as e:
            print(f"[WEB ERROR] Emit failed: {e}")

def update_stats(new_stats):
    global stats_data
    with lock:
        stats_data.update(new_stats)
    # Optional: Emit stats via socketio too for real-time updates
    try:
        socketio.emit('stats_update', stats_data)
    except:
        pass

def generate_frames():
    global outputFrame, lock
    while True:
        with lock:
            if outputFrame is None:
                continue
            (flag, encodedImage) = cv2.imencode(".jpg", outputFrame)
            if not flag:
                continue
        yield(b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + bytearray(encodedImage) + b'\r\n')
        time.sleep(0.05)

@app.route("/")
@login_required
def index():
    if current_user.role == 'user':
        return redirect(url_for('mobile_nav'))
    else:
        # Guardian logic
        if not current_user.linked_user_id:
            return render_template("dashboard.html", user=current_user, show_bind_modal=True)
        return render_template("dashboard.html", user=current_user, show_bind_modal=False)

@app.route("/mobile")
@login_required
def mobile_nav():
    global nav_state
    return render_template("mobile_nav.html", user=current_user, active_tab='nav', nav_state=nav_state)

@app.route("/mobile/history")
@login_required
def mobile_history():
    # Fetch logs related to this user OR all logs if system wide
    logs = LogRecord.query.order_by(LogRecord.timestamp.desc()).limit(50).all()
    return render_template("mobile_history.html", user=current_user, logs=logs, active_tab='history')

@app.route("/mobile/settings")
@login_required
def mobile_settings():
    return render_template("mobile_settings.html", user=current_user, active_tab='settings')


@app.route("/video_feed")
@login_required
def video_feed():
    # Maintain legacy feed for compatibility
    return Response(generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

# API for Guardian Config
@app.route('/api/config', methods=['GET', 'POST'])
@login_required
def handle_config():
    if current_user.role != 'guardian':
        return jsonify({'error': 'Unauthorized'}), 403
        
    global remote_config
    if request.method == 'POST':
        data = request.json
        if 'sensitivity' in data:
            try:
                # Update global config
                remote_config['sensitivity'] = float(data['sensitivity'])
                # Also log this action
                with lock:
                    timestamp = time.strftime("%H:%M:%S")
                    stats_data['logs'].insert(0, {
                        "time": timestamp, 
                        "cat": "CONFIG", 
                        "msg": f"{current_user.username} 调整灵敏度为: {remote_config['sensitivity']}"
                    })
                    add_db_log("CONFIG", f"{current_user.username} 调整灵敏度为: {remote_config['sensitivity']}", current_user.id)
            except ValueError:
                pass
        return jsonify({'status': 'ok', 'config': remote_config})
    
    return jsonify(remote_config)

@app.route("/api/speak", methods=['POST'])
@login_required
def remote_speak():
    if current_user.role != 'guardian':
         return jsonify({"status": "error", "message": "权限不足"}), 403

    data = request.json
    text = data.get('text', '')
    is_sos = data.get('sos', False)
    
    if text:
        with lock:
            # Struct: {'text': str, 'sos': bool}
            remote_speech_queue.append({"text": text, "sos": is_sos})
            
            timestamp = time.strftime("%H:%M:%S")
            cat = "SOS" if is_sos else "REMOTE"
            msg = f"发送SOS警报！内容: {text}" if is_sos else f"{current_user.username}: {text}"
            
            stats_data['logs'].insert(0, {"time": timestamp, "cat": cat, "msg": msg})
            add_db_log(cat, msg, current_user.id)
            
    return jsonify({"status": "ok"})

@app.route("/api/stats")
@login_required
def get_stats():
    with lock:
        return jsonify(stats_data)

@app.route("/history")
@login_required
def history():
    logs = LogRecord.query.order_by(LogRecord.timestamp.desc()).limit(100).all()
    return render_template("history.html", user=current_user, logs=logs)

@app.route("/settings", methods=['GET', 'POST'])
@login_required
def settings():
    if current_user.role != 'guardian':
        return redirect(url_for('index'))
    
    setting = GuardianSetting.query.filter_by(guardian_id=current_user.id).first()
    if not setting:
        setting = GuardianSetting(guardian_id=current_user.id)
        db.session.add(setting)
        db.session.commit()

    if request.method == 'POST':
        setting.sensitivity = float(request.form.get('sensitivity', 0.3))
        setting.dark_mode = 'dark_mode' in request.form
        setting.battery_alarm_threshold = float(request.form.get('battery_alarm_threshold', 20.0))
        setting.latency_alarm_threshold = float(request.form.get('latency_alarm_threshold', 200.0))
        db.session.commit()
        # Sync
        global remote_config
        remote_config['sensitivity'] = setting.sensitivity
        add_db_log("CONFIG", f"修改了监控设置（灵敏度等）", current_user.id)
        return redirect(url_for('settings'))

    return render_template("settings.html", user=current_user, setting=setting)

def start_server(host="0.0.0.0", port=5000):
    # Use socketio.run instead of app.run
    # HTTPS is required for mobile browser GPS (high accuracy)
    try:
        import ssl
        print(f"Starting SocketIO Server (HTTPS) on {host}:{port}")
        print(f"  手机访问地址: https://<你的IP>:{port}/mobile")
        print(f"  注意: 浏览器会提示'不安全'，请点击'高级'->'继续访问'")
        socketio.run(app, host=host, port=port, debug=False, use_reloader=False, ssl_context='adhoc')
    except ImportError:
        print(f"[WARNING] pyopenssl 未安装，降级为 HTTP 模式 (GPS精度可能受限)")
        print(f"Starting SocketIO Server (HTTP) on {host}:{port}")
        socketio.run(app, host=host, port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    start_server()

