import cv2
import numpy as np
import time
from ultralytics import YOLO
from config import SEG_MODEL_PATH, CLASS_NAMES_CN

class BlindPathNavigator:
    def __init__(self):
        print(f"[NAV] Initializing V6 (Tuned)...")
        try:
            import os
            onnx_path = SEG_MODEL_PATH.replace('.pt', '.onnx')
            if os.path.exists(onnx_path):
                 print(f"[NAV] Found ONNX model: {onnx_path}. Using ONNX Runtime.")
                 self.model = YOLO(onnx_path, task='segment')
            else:
                 print(f"[NAV] Loading PyTorch model from {SEG_MODEL_PATH}...")
                 self.model = YOLO(SEG_MODEL_PATH) 
            
            print("[NAV] Model loaded.")
        except Exception as e:
            print(f"[NAV] Error: {e}")
            self.model = None

        self.last_guidance_time = 0
        self.last_cmd = ""
        self.is_approaching_intersection = False

    def set_intersection_mode(self, is_approaching):
        """Called by main loop to sync MapAgent state"""
        self.is_approaching_intersection = is_approaching

    def process_frame(self, frame, detections=[]):
        try:
            original_h, original_w = frame.shape[:2]
            
            # 1. Resize for Consistent Logic (640 width)
            # REVERTED LOGIC: Config now handles resizing. frame is already small (320px).
            # But we kept "proc_frame" logic. Let's simplify and just use frame.
            proc_frame = frame
            proc_h, proc_w = frame.shape[:2]
            
            # Optimization: Skip Segmentation (Run every 3 frames)
            if not hasattr(self, 'seg_frame_count'): self.seg_frame_count = 0
            self.seg_frame_count += 1
            
            # Only run segmentation every 3rd frame to save FPS
            # On other frames, use cached mask if available
            if self.seg_frame_count % 3 == 0 or not hasattr(self, 'last_mask'):
                blind_path_mask = self._get_segmentation_mask(proc_frame)
                self.last_mask = blind_path_mask
            else:
                blind_path_mask = self.last_mask

            centerX = proc_w // 2
            annotated_frame = proc_frame.copy()
            guidance_text = ""
            
            if not self.model: 
                return "Model Not Loaded", frame

            # 2. OBSTACLES (Priority 1)
            # Visualize all detections around
            for det in detections:
                 x1, y1, x2, y2 = det['box']
                 label = CLASS_NAMES_CN.get(det['class_id'], "Obj")
                 cv2.rectangle(annotated_frame, (int(x1), int(y1)), (int(x2), int(y2)), (100, 100, 100), 1)
                 cv2.putText(annotated_frame, label, (int(x1), int(y1)-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100,100,100), 1)

            danger_cmd, debug_danger = self._check_obstacles(detections, original_w, original_h)
            if danger_cmd:
                cv2.putText(annotated_frame, f"ALARM: {debug_danger}", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)
                final_frame = cv2.resize(annotated_frame, (original_w, original_h))
                self.last_cmd = debug_danger
                return danger_cmd, final_frame

            # 3. BLIND PATH
            # blind_path_mask is already set at the top with skipping logic
            pass
            
            if blind_path_mask is not None:
                if blind_path_mask.shape[:2] != (proc_h, proc_w):
                    blind_path_mask = cv2.resize(blind_path_mask, (proc_w, proc_h), interpolation=cv2.INTER_NEAREST)

                # Viz
                color_mask = np.zeros_like(proc_frame)
                color_mask[blind_path_mask > 0] = [0, 255, 0]
                annotated_frame = cv2.addWeighted(annotated_frame, 1, color_mask, 0.4, 0)
                
                # --- LOGIC V5: "Rule of Thirds" ---
                # Zone 1: Centering (Grey Box) logic.
                # Zone 2: Alignment logic.
                
                # Use Bottom 1/3 for "Feet" location
                h_split = proc_h // 3
                mask_bottom = blind_path_mask[2*h_split:, :]
                
                cX_bottom, cY_bottom = self._get_centroid(mask_bottom)
                if cY_bottom != -1: cY_bottom += 2*h_split
                
                # Fallback to mid if bottom empty
                if cX_bottom == -1:
                    mask_mid = blind_path_mask[h_split:2*h_split, :]
                    cX_bottom, cY_bottom = self._get_centroid(mask_mid)
                    if cY_bottom != -1: cY_bottom += h_split

                if cX_bottom != -1:
                    # Draw Feet Point
                    cv2.circle(annotated_frame, (cX_bottom, cY_bottom), 15, (0, 255, 255), -1)
                    
                    # 1. CHECK SAFE ZONE
                    offset = cX_bottom - centerX
                    limit_pos = proc_w * 0.165 # +/- 16.5% = 33% total width
                    in_safe_zone = abs(offset) <= limit_pos
                    
                    # Visualizing the Safe Zone Box
                    zone_color = (0, 255, 0) if in_safe_zone else (0, 0, 255) # Green if in, Red if out
                    box_w = int(limit_pos)
                    cv2.rectangle(annotated_frame, (centerX-box_w, proc_h-20), (centerX+box_w, proc_h), zone_color, 3)

                    if not in_safe_zone:
                        # --- MODE: SHIFT ---
                        if offset < 0:
                            cmd_voice = "向左平移"
                            cmd_debug = "<< SHIFT LEFT"
                            cv2.arrowedLine(annotated_frame, (centerX, cY_bottom), (cX_bottom, cY_bottom), (0,255,255), 4)
                        else:
                            cmd_voice = "向右平移"
                            cmd_debug = "SHIFT RIGHT >>"
                            cv2.arrowedLine(annotated_frame, (centerX, cY_bottom), (cX_bottom, cY_bottom), (0,255,255), 4)
                    else:
                        # --- MODE: ALIGN ---
                        # Get Top Point
                        mask_top = blind_path_mask[:h_split, :]
                        cX_top, cY_top = self._get_centroid(mask_top)
                        
                        if cX_top != -1:
                            cv2.circle(annotated_frame, (cX_top, cY_top), 10, (255, 0, 255), -1)
                            cv2.line(annotated_frame, (cX_bottom, cY_bottom), (cX_top, cY_top), (255, 0, 0), 3)
                            
                            tilt = cX_top - cX_bottom
                            # Threshold for turning: Relaxed to 15%
                            limit_tilt = proc_w * 0.15
                            
                            if tilt > limit_tilt:
                                cmd_voice = "向右微调"
                                cmd_debug = "TURN RIGHT"
                                cv2.ellipse(annotated_frame, (centerX, proc_h-50), (40,40), 0, 0, 90, (0,165,255), 4)
                            elif tilt < -limit_tilt:
                                cmd_voice = "向左微调"
                                cmd_debug = "TURN LEFT"
                                cv2.ellipse(annotated_frame, (centerX, proc_h-50), (40,40), 0, 180, 270, (0,165,255), 4)
                            else:
                                cmd_voice = "直行"
                                cmd_debug = "STRAIGHT"
                                cv2.line(annotated_frame, (centerX, proc_h//2+20), (centerX, proc_h//2-20), (0,255,0), 6)
                        else:
                            # Verify if path is straight based on what we have
                            cmd_voice = "直行"
                            cmd_debug = "STRAIGHT"

                    self.last_cmd = cmd_debug
                    guidance_text = cmd_voice # Direct return
                else: 
                     # FREE WALKING MODE: If path exists but no bottom, same logic.
                     guidance_text = ""
                     self.last_cmd = "SEARCHING"

            else:
                # FREE WALKING MODE: No path found. Silence.
                guidance_text = "" 
                self.last_cmd = "FREE WALK"

            self._draw_ui(annotated_frame, self.last_cmd, proc_w, proc_h)
            
            final_frame = cv2.resize(annotated_frame, (original_w, original_h))
            return guidance_text, final_frame

        except Exception as e:
            err_msg = str(e)
            print(f"[NAV EXCEPTION] {err_msg}")
            return "错误", frame

    def _get_centroid(self, mask_slice):
        M = cv2.moments(mask_slice)
        if M["m00"] == 0: return -1, -1
        cX = int(M["m10"] / M["m00"])
        cY = int(M["m01"] / M["m00"])
        return cX, cY

    def _draw_ui(self, frame, cmd, w, h):
        if cmd:
            color = (0, 255, 0)
            if "SHIFT" in cmd: color = (0, 255, 255)
            if "TURN" in cmd: color = (0, 165, 255)
            if "ALARM" in cmd or "AVOID" in cmd: color = (0, 0, 255)
            if "RED" in cmd: color = (0, 0, 255)
            cv2.putText(frame, f"{cmd}", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3)

    def _check_obstacles(self, detections, w, h):
        if not detections: return None, None
        
        # Obstacle Logic: Zone narrowed to Center 25% - 75%
        box_x_min = w * 0.25 
        box_x_max = w * 0.75 
        
        # Traffic Light Logic (Class 9) prioritized first if at intersection
        traffic_light_status = None
        for det in detections:
            if det['class_id'] == 9:
                tl_color = det.get('tl_color', 'Unknown')
                if tl_color == 'Red':
                    traffic_light_status = "RED"
                elif tl_color == 'Green':
                    traffic_light_status = "GREEN"
                    
        # Intersection specific logic
        if self.is_approaching_intersection:
            if traffic_light_status == 'RED':
                return "警告！当前路口红灯亮起，请务必停止通行", "RED LIGHT STOP"
            elif traffic_light_status == 'GREEN':
                # Check for obstacles in the crosswalk area (bottom 50% of screen)
                clear_crosswalk = True
                for det in detections:
                    if det['class_id'] in [0, 1, 2, 5, 7]: # People, Cars
                        _, y1, _, y2 = det['box']
                        cy = (y1 + y2) / 2
                        if cy > h * 0.5: # Obstacle is close
                            clear_crosswalk = False
                            break
                if clear_crosswalk:
                    return "绿灯亮起。请起步通行，注意倾听可能出现的转弯车辆", "GREEN LIGHT GO"
            else:
                 pass
        else:
            # Normal walking: Only react to Red light urgently, ignore Green
            if traffic_light_status == 'RED':
                 return "注意！前方红光停止信号，请留步", "RED LIGHT STOP"
                 
        for det in detections:
            cls_id = det['class_id']
            if cls_id == 9: continue # Handled above

            # Obstacles
            if cls_id in [0, 1, 2, 5, 7]: 
                x1, y1, x2, y2 = det['box']
                cx = (x1 + x2) / 2
                
                if box_x_min < cx < box_x_max:
                    area = (x2-x1)*(y2-y1)/(w*h)
                    
                    # LOGIC TUNING: 
                    # User requested to prioritize Blind Path unless obstacle is "Large enough"
                    # Previous: 0.20 (20%) -> New: 0.10 (10%) to be more sensitive
                    if area > 0.10:
                        obj_name = CLASS_NAMES_CN.get(cls_id, "障碍物")
                        
                        # Direction logic
                        if cx < w/2: return f"警告！正前方有{obj_name}阻挡，请向右侧微微绕行", f"AVOID {obj_name} >"
                        else: return f"警告！正前方有{obj_name}阻挡，请向左侧微微绕行", f"< AVOID {obj_name}"
                    elif area > 0.05:
                        # Optional: Draw Yellow box for small obstacles but DO NOT return avoid command
                        # This lets Blind Path logic take over
                        pass

        return None, None
        return None, None

    def _get_segmentation_mask(self, frame):
        try:
            import config
            imgsz = getattr(config, 'YOLO_INFERENCE_SIZE', 320)
            results = self.model.predict(frame, conf=0.25, verbose=False, imgsz=imgsz)
            if not results: return None
            result = results[0]
            if not result.masks: return None
            
            best_mask = None
            max_area = 0
            for mask in result.masks.data:
                m = mask.cpu().numpy().astype('uint8')
                area = np.sum(m)
                if area > max_area:
                    max_area = area
                    best_mask = m
            return best_mask
        except:
            return None
