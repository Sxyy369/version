import cv2
import time
import threading
import sys
import os
from config import CAMERA_ID, CLASS_NAMES_CN, COLOR_SAFE, COLOR_WARN, COLOR_DANGER
import config
from src.detection import YOLO11Detector
from src.warning import WarningSystem
from src.navigator import BlindPathNavigator # Phase 5: Navigation
from src.geo_navigation import GeoNavigator # Phase 6: Map Navigation
from src.voice_agent import VoiceAgent # Phase 6: Voice Interaction


# Phase 4: Web Monitoring
try:
    from web.app import start_server, update_frame, update_stats, remote_speech_queue
    WEB_MONITOR_AVAILABLE = True
except ImportError as e:
    WEB_MONITOR_AVAILABLE = False
    print(f"Web monitoring module not found: {e}")

# Phase 2/3 Modules: Independent Loading
ocr_module = None
tts_module = None
llm_module = None

# 1. Try Import TTS
try:
    from src.tts_engine import AudioAnnouncer
    tts_module = AudioAnnouncer
    print("[INIT] TTS Module loaded.")
except ImportError as e:
    print(f"[WARNING] TTS Module not found: {e}")

# 2. Try Import OCR
try:
    from src.ocr_engine import TextRecognizer
    ocr_module = TextRecognizer
    print("[INIT] OCR Module loaded.")
except ImportError as e:
    print(f"[WARNING] OCR Module not found: {e}")

# 3. Try Import LLM Agent
try:
    from src.llm_agent import LLMAgent
    llm_module = LLMAgent
    print("[INIT] LLM Agent loaded.")
except ImportError as e:
    print(f"[WARNING] LLM Module not found: {e}")

def main():
    print("Initializing Smart Blind Assist System...")
    
    # Flags to track module availability
    tts_available = False
    ocr_available = False
    
    # Start Web Server (Phase 4)
    if WEB_MONITOR_AVAILABLE:
        print("Starting Monitor Server at https://localhost:5000 ...")
        server_thread = threading.Thread(target=start_server, kwargs={'host':'0.0.0.0', 'port':5000}, daemon=True)
        server_thread.start()
    
    # 1. Initialize Modules
    try:
        # Core Detection
        detector = YOLO11Detector()
        warning_sys = WarningSystem()
        
        # Initialize Navigator
        navigator = BlindPathNavigator()
        # Check if model loaded
        navigator_available = navigator.model is not None
        
        tts = None
        ocr = None
        ai_agent = None
        geo_nav = None
        voice_agent = None
        last_voice_trigger_time = 0 # Debounce for voice key

        # Initialize GeoNavigator
        try:
            from web.app import get_current_gps
            geo_nav = GeoNavigator(
                api_key=getattr(config, 'AMAP_API_KEY', None),
                gps_callback=get_current_gps
            )
            print("[INIT] Geo Navigation Module loaded (with Phone GPS support).")
        except Exception as e:
            print(f"[ERROR] Geo Nav Init Failed: {e}")

        # Initialize Voice Agent
        try:
            voice_agent = VoiceAgent()
            print("[INIT] Voice Agent Module loaded.")
        except Exception as e:
            print(f"[ERROR] Voice Agent Init Failed: {e}")


        # Try initializing TTS
        if tts_module:
            try:
                tts = tts_module()
                tts_available = True
                tts.speak("系统启动中，请稍候", priority=0)
            except Exception as e:
                print(f"[ERROR] TTS Init Failed: {e}")
                tts_available = False

        # Try initializing OCR separately
        if ocr_module:
            try:
                ocr = ocr_module() # Heavy load
                ocr_available = True
                print("[INIT] OCR Initialized Successfully.")
            except Exception as e:
                print(f"[ERROR] OCR Init Failed: {e}")
                print("Suggestion: check rapidocr_onnxruntime installation.")
                ocr_available = False
        else:
             print("[INFO] OCR feature disabled (module missing).")

        # Try initializing LLM Agent (Phase 3)
        if llm_module:
            try:
                ai_agent = llm_module()
                print("[INIT] LLM Agent Initialized.")
            except Exception as e:
                print(f"[ERROR] LLM Init Failed: {e}")

        # System Ready Announcement
        if tts_available:
            status_msg = "系统就绪"
            if not ocr_available:
                status_msg += "，文字识别不可用"
            tts.speak(status_msg, priority=0)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error initializing modules: {e}")
        return

    # 2. Open Video Source
    cap = cv2.VideoCapture(CAMERA_ID)

    if not cap.isOpened():
        print(f"Error: Could not open video source {CAMERA_ID}")
        return

    print("System started. Press 'q' to exit. Press 't' to read text.")

    ocr_trigger = False
    ocr_speaking_until = 0.0 # Timestamp to pause warnings while OCR is speaking
    
    # Track last spoken command to decide interruption
    last_spoken_text = ""
    last_nav_speak_time = 0.0

    # Stats tracking
    global_stats = {
        "warnings_count": 0,
        "detection_counts": {},
        "current_risks": [],
        "logs": [],
        "snapshots": [], 
        "status": "Running",
        "fps": 0,
        "heatmap": [[0]*10 for _ in range(10)],
        "warning_history": []
    }

    # FPS Calculation
    prev_frame_time = 0
    new_frame_time = 0
    
    # History timer
    last_history_update = time.time()

    def log_message(category, text):
        """Add message to global logs (keep last 10)"""
        timestamp = time.strftime("%H:%M:%S")
        entry = {"time": timestamp, "cat": category, "msg": text}
        global_stats["logs"].insert(0, entry)
        if len(global_stats["logs"]) > 20: # Keep last 20
            global_stats["logs"].pop()

    # Snapshot Helper
    def save_snapshot(frame, tag):
        """Save frame to snapshot dir and log it"""
        import uuid
        from config import SNAPSHOT_DIR
        
        filename = f"{int(time.time())}_{tag}_{uuid.uuid4().hex[:6]}.jpg"
        filepath = os.path.join(SNAPSHOT_DIR, filename)
        try:
            cv2.imwrite(filepath, frame)
            # Log for web
            global_stats["snapshots"].insert(0, {
                "time": time.strftime("%H:%M:%S"), 
                "tag": tag, 
                "url": f"/static/snapshots/{filename}"
            })
            if len(global_stats["snapshots"]) > 10:
                global_stats["snapshots"].pop()
        except Exception as e:
            print(f"Snapshot Error: {e}")

    # Frame Counter for skipping
    frame_count = 0
    last_detections = []
    
    while True:
        # FPS Calculation
        new_frame_time = time.time()
        fps = 1/(new_frame_time-prev_frame_time) if prev_frame_time > 0 else 0
        prev_frame_time = new_frame_time
        global_stats["fps"] = int(fps)

        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame")
            break

        # Capture original dimensions
        original_h, original_w = frame.shape[:2]

        # PERFORMANCE OPTIMIZATION: Resize to target width for processing
        # This ensures consistent speed regardless of camera resolution (1080p/4K)
        target_width = getattr(config, 'VIDEO_WIDTH_TARGET', 320) # Default to 320
        if original_w > target_width:
            scale = target_width / original_w
            new_height = int(original_h * scale)
            frame_small = cv2.resize(frame, (target_width, new_height))
        else:
            frame_small = frame.copy()
        
        # Use frame_small for all processing
        frame = frame_small
        
        frame_height, frame_width = frame.shape[:2]
        frame_area = frame_height * frame_width
        
        # Ensure we use the global time module
        current_now = time.time()
        
        # Handle Dynamic Config from Web
        if WEB_MONITOR_AVAILABLE:
            from web.app import get_latest_config
            new_conf = get_latest_config()
            if new_conf:
                # Update warning config, default 0.3
                try:
                     val = float(new_conf.get('sensitivity', 0.3))
                     config.WARNING_AREA_THRESHOLD = val
                except:
                    pass
        
        # 3. Detection with DYNAMIC Frame Skipping
        frame_count += 1
        
        skip_interval = getattr(config, 'FRAME_SKIP', 1)
        if frame_count % skip_interval == 0:
            detections = detector.detect(frame)
            last_detections = detections
        else:
            detections = last_detections
            
        # --- UNIFIED NAVIGATION LOGIC (Default) ---
        if navigator_available:
             # Pass detections to navigator for fusion logic
             nav_text, nav_frame = navigator.process_frame(frame, detections)
             frame = nav_frame 
             
             # Voice Logic
             if tts_available and tts:
                 if nav_text:
                     # If we have something to say (Obstacle OR Path Guidance)
                     # New Logic: Send to queue even if busy? 
                     # With caching, we can afford to queue them, but we should avoid spamming the EXACT same message.
                     if nav_text != last_spoken_text:
                         # Dynamic Priority: Danger interrupts, Info waits
                         # Geo Nav is 0.5. 
                         # So Danger (0) > Geo Nav (0.5) > Path Info (1)
                         prio = 1
                         if "障碍" in nav_text or "注意" in nav_text or "停止" in nav_text or "警告" in nav_text:
                             prio = 0
                             
                         tts.speak(nav_text, priority=prio)
                         
                         if WEB_MONITOR_AVAILABLE:
                             from web.app import socketio
                             socketio.emit('voice_msg', {'text': nav_text, 'priority': prio})
                             
                         last_spoken_text = nav_text
                         log_message("NAV", nav_text)
                     elif not tts.is_busy():
                         # Repeat same message only if idle
                         tts.speak(nav_text, priority=1)
                         if WEB_MONITOR_AVAILABLE:
                             from web.app import socketio
                             socketio.emit('voice_msg', {'text': nav_text, 'priority': 1})
                 else:
                     # nav_text is empty (Free Walking Mode, Safe)
                     pass

        else:
             # Fallback if module failed
             cv2.putText(frame, "NAV ERROR", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)
        
        # Update Web Stats (Detections)
        for det in detections:
            cls_name = CLASS_NAMES_CN.get(det['class_id'], "Unk")
            global_stats["detection_counts"][cls_name] = global_stats["detection_counts"].get(cls_name, 0) + 1
        
        # 4. Warning Logic
        # NOTE: Navigator V6 handles obstacles better, so we use WarningSystem mostly for Web Viz now.
        risks = []
        for det in detections:
            x1, y1, x2, y2 = det['box']
            cls_id = det['class_id']
            box_area = (x2 - x1) * (y2 - y1)
            
            # Draw Box
            color = COLOR_SAFE
            label = f"{CLASS_NAMES_CN.get(cls_id, cls_id)}"
            
            # Update Heatmap (Grid 10x10)
            if WEB_MONITOR_AVAILABLE:
                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)
                grid_x = min(9, int(cx / frame_width * 10))
                grid_y = min(9, int(cy / frame_height * 10))
                global_stats["heatmap"][grid_y][grid_x] += 1
            
            # Traffic Light Status
            if cls_id == 9 and det['tl_color'] != "Unknown":
                label += f" [{det['tl_color']}]"
                if det['tl_color'] == 'Red': color = COLOR_DANGER
                elif det['tl_color'] == 'Green': color = COLOR_SAFE
                elif det['tl_color'] == 'Yellow': color = COLOR_WARN
            
            # Check Collision Risk (Dynamic Threshold)
            is_risk = warning_sys.check_collision_risk(box_area, frame_area, cls_id)
            if is_risk:
                color = COLOR_DANGER
                extra_info = det.get('tl_color') if cls_id == 9 else None
                risks.append((cls_id, box_area / frame_area, extra_info))
                label += " !WARNING!"

            # Render (Only if Navigator didn't already render it? Navigator draws gray boxes)
            # We can overlay colored boxes for web monitor
            # cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            # cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            pass 

        # Update Risks Stats
        global_stats["current_risks"] = [
            (CLASS_NAMES_CN.get(r[0], "Unk"), r[1]) for r in risks
        ]
        # 5. Global Warning Message -> TTS (Priority 0)
        # DISABLE OLD WARNING SYSTEM VOICE to avoid conflict with Navigator
        # if current_now > ocr_speaking_until:
        #     if tts_available and tts and not tts.is_busy():
        #         msg = warning_sys.generate_warning_message(risks)
        #         if msg:
        #             # Log Warning (Always, if meaningful)
        #             global_stats["warnings_count"] += 1
        #             log_message("WARNING", msg)
        #             
        #             # Print to console (Always)
        #             print(f"[VOICE] {msg}")

        #             # Voice Warning
        #             if tts_available and tts and not tts.is_busy():
        #                 tts.speak(msg, priority=0)
            
        #     # Visual warning
        #     is_visual_warning = any(r[1] > 0.05 for r in risks)
        #     if is_visual_warning:
        #         cv2.putText(frame, "WARNING", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, COLOR_DANGER, 3)

        # 6. OCR Trigger Logic -> TTS (Priority 1)
        if ocr_trigger:
            print("[OCR] Triggered...")
            ocr_speaking_until = time.time() + 5.0
            
            # Save Snapshot
            save_snapshot(frame.copy(), "OCR")

            if ocr_available and ocr and tts_available and tts:
                def run_ocr(img_frame):
                    texts = ocr.recognize(img_frame)
                    
                    # 1. OCR Blacklist Filter (Screen UI text)
                    OCR_BLACKLIST = ["FPS", "Free Walk", "Connected", "Inside Link", "GPS", "Smart Blind", "Link"]
                    filtered_texts = []
                    if texts:
                        for t in texts:
                             # Skip empty or blacklisted
                             if not t.strip(): continue
                             if any(b.lower() in t.lower() for b in OCR_BLACKLIST): continue
                             # Skip pure numbers (often clock or fps)
                             if t.replace('.', '').isdigit(): continue
                             filtered_texts.append(t)
                    
                    if filtered_texts:
                        full_text = "发现文字：" + "，".join(filtered_texts)
                        print(f"[OCR Result] {full_text}")
                        # Force speak OCR
                        tts.interrupt()
                        time.sleep(0.1)
                        tts.speak(full_text, priority=0) 
                        log_message("OCR", full_text)
                    else:
                        # Don't speak "No text found" if we just filtered everything out
                        # tts.speak("未发现文字", priority=0)
                        log_message("OCR", "未检测到有效文字 (已过滤)")
                
                ocr_thread = threading.Thread(target=run_ocr, args=(frame.copy(),))
                ocr_thread.start()
            elif not ocr_available:
                 print("[ERROR] OCR module is not initialized.")
                 if tts_available and tts:
                     tts.speak("文字识别功能不可用", priority=0)
            
            ocr_trigger = False

        # Phase 4: Update Web Server
        if WEB_MONITOR_AVAILABLE:
            # 1. Remote Speech/SOS Check
            if remote_speech_queue and tts_available and tts:
                try:
                    cmd_obj = remote_speech_queue.pop(0)
                    # Support both string (legacy) and dict (new)
                    if isinstance(cmd_obj, dict):
                        text = cmd_obj.get('text')
                        is_sos = cmd_obj.get('sos', False)
                    else:
                        text = cmd_obj
                        is_sos = False
                        
                    print(f"[REMOTE] Speaking: {text}")
                    if is_sos:
                        # Shout!
                        for _ in range(3): 
                            tts.interrupt()
                            tts.speak(f"紧急警告！{text}", priority=0)
                            time.sleep(1.5)
                    else:
                        tts.interrupt()
                        tts.speak(text, priority=0)
                except IndexError:
                    pass
            
            # 2. History Update
            if time.time() - last_history_update > 5:
                timestamp = time.strftime("%H:%M:%S")
                global_stats["warning_history"].append({"time": timestamp, "value": global_stats["warnings_count"]})
                if len(global_stats["warning_history"]) > 12:
                    global_stats["warning_history"].pop(0)
                last_history_update = time.time()

            update_frame(frame)
            update_stats(global_stats)

        # Display
        try:
            # Scale up for display visibility (keep processing resolution low)
            # Use INTER_NEAREST to make pixels obvious (user requested lower clarity)
            # Restore to ORIGINAL capture size so window size is unchanged.
            if frame.shape[1] < original_w:
                display_frame = cv2.resize(frame, (original_w, original_h), interpolation=cv2.INTER_NEAREST)
            else:
                 display_frame = frame
            
            # print("[DEBUG] Showing video frame...") # Uncomment if needed, but might spam
            cv2.imshow("Smart Blind Assist - Phase 2", display_frame)
        except Exception as e:
            print(f"[ERROR] GUI Error: {e}")

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("[INFO] Quit signal received.")
            break
        elif key == ord('t'):
            ocr_trigger = True
        elif key == ord('d'): # AI Agent logic remains same
            save_snapshot(frame.copy(), "AI") # Save snapshot
            
            if tts_available and tts:
                tts.speak("正在帮您看，请稍候...", priority=0)
            
            if ai_agent:
                def speak_result(text):
                    print(f"[AI Assistant] {text}")
                    log_message("AI", text)
                    if tts_available and tts:
                        tts.speak(text, priority=0)
                
                ai_agent.analyze_scene_async(frame.copy(), speak_result)
            else:
                 if tts_available and tts:
                    tts.speak("智能助手不可用", priority=0)
        
        elif key == ord('v'): # Voice Command Mode
            # Debounce: Prevent double trigger
            if time.time() - last_voice_trigger_time < 2.0:
                continue
            last_voice_trigger_time = time.time()
            
            print("[USER] Voice Command Triggered")
            
            # Stop any ongoing speech first!
            if tts_available and tts:
                 tts.interrupt()
                 
            if tts_available and tts:
                # 1. Prompt user to speak
                tts.speak("我在听，请下达指令...", priority=0)
                # Brief pause to led TTS finish "listening"
                # Ideally check is_busy but sleep is safer for now
                time.sleep(1.5) 
            
            if voice_agent:
                # 2. Listen
                text = voice_agent.listen_once()
                if text:
                    print(f"[VOICE] User said: {text}")
                    intent, content = voice_agent.classify_intent(text)
                    
                    # Handle "Navigation without destination"
                    if intent == "NAV_ASK_DEST":
                        if tts_available and tts:
                            tts.speak("请问要去哪里？", priority=0)
                            time.sleep(1.5)
                        
                        # Listen again for destination
                        dest_text = voice_agent.listen_once()
                        if dest_text:
                            print(f"[VOICE] Destination provided: {dest_text}")
                            intent = "NAV"
                            content = dest_text
                        else:
                            if tts_available and tts:
                                tts.speak("没有听到地点，已取消", priority=0)
                            continue


                    # NEW: Query Location
                    elif intent == "QUERY_LOCATION":
                        # 使用纠偏后的 GPS 获取当前地址
                        from web.app import get_current_gps
                        curr_gps = get_current_gps()
                        if curr_gps:
                            loc_str = f"{curr_gps['lon']},{curr_gps['lat']}"
                            # 优先尝试从 MapAgent 获取吸附后的位置描述（如果在导航中）
                            if geo_nav.is_navigating and hasattr(map_agent, 'nav_steps'):
                                # 这里获取实时吸附后的描述
                                address = geo_nav.get_regeo_address(loc_str)
                                tts.speak(f"您在路线附近，当前位置是{address}", priority=0)
                            else:
                                address = geo_nav.get_regeo_address(loc_str)
                                tts.speak(f"当前定位在{address}", priority=0)
                        else:
                            tts.speak("暂时无法获取当前位置", priority=0)

                    # NEW: Navigation Control (同步到 MapAgent)
                    elif intent == "NAV_CONTROL":
                        # 直接查询 app.py 里的 map_agent 状态
                        from web.app import get_map_agent
                        ma = get_map_agent()
                        if ma and ma.current_route:
                            msg = ""
                            if content == "NEXT":
                                # 同步步骤
                                ma.current_step_index += 1
                                if ma.current_step_index < len(ma.nav_steps):
                                    msg = ma.nav_steps[ma.current_step_index]["instruction"]
                                else:
                                    msg = "导航已到终点"
                            elif content == "REPEAT":
                                if ma.current_step_index < len(ma.nav_steps):
                                    msg = ma.nav_steps[ma.current_step_index]["instruction"]
                                else:
                                    msg = "导航已结束"
                            elif content == "STOP":
                                from web.app import nav_state
                                nav_state["is_navigating"] = False
                                ma.current_route = None
                                msg = "已结束导航"
                                
                            if msg:
                                tts.speak(msg, priority=0.5)
                        else:
                             tts.speak("当前未在导航中", priority=0)

                    elif intent == "NAV":
                        # 使用 MapAgent 进行搜索和规划，确保 Web 端同步
                        from web.app import get_map_agent, nav_state, get_current_gps
                        ma = get_map_agent()
                        curr_gps = get_current_gps()
                        
                        if ma:
                            if isinstance(content, dict):
                                target_dest = content.get("dest")
                            else:
                                target_dest = content
                            
                            tts.speak(f"正在前往{target_dest}，请稍候...", priority=0)
                            
                            # 1. 获取当前纠偏位置
                            if not curr_gps:
                                tts.speak("定位未就绪，请稍后再试", priority=0)
                                continue
                            
                            curr_loc = f"{curr_gps['lon']},{curr_gps['lat']}"
                            
                            # 2. 搜索并规划
                            res = ma.search_location(target_dest)
                            if res:
                                name, loc = res
                                msg = ma.get_walking_route(curr_loc, loc)
                                nav_state["is_navigating"] = True
                                nav_state["destination"] = name
                                tts.speak(f"已为您规划去{name}的路线。{msg}", priority=0)
                                log_message("NAV", f"语音启动导航: {name}")
                            else:
                                tts.speak(f"没找到地点：{target_dest}", priority=0)
                        else:
                            tts.speak("导航模块异常", priority=0)
                            
                    elif intent == "CHAT":
                        log_message("CHAT", f"问: {text}")
                        # Use LLM for chat if available
                        if ai_agent:
                            tts.speak("正在思考...", priority=0)
                            def chat_callback(response_text):
                                print(f"[AI Chat] {response_text}")
                                log_message("CHAT", f"答: {response_text}")
                                if tts_available and tts:
                                    tts.speak(response_text, priority=0)

                            ai_agent.analyze_scene_async(frame.copy(), chat_callback, query=text)
                        
                        else:
                            tts.speak("智能助手未连接", priority=0)
                else:
                    if tts_available and tts:
                        tts.speak("没听清，请再说一次", priority=0)
            else:
                if tts_available and tts:
                    tts.speak("语音模块故障", priority=0)

        # check for navigation guidance updates (Removed auto-advance)
        # But we might want to remind user if they are idle for too long?
        # For now, strictly manual.
        
    # Cleanup
    if tts_available and tts:
        tts.stop()
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
