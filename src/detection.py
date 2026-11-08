import cv2
import os
from ultralytics import YOLO
from config import TARGET_CLASSES, CONF_THRESHOLD, YOLO_MODEL_PATH
from src.traffic_light import analyze_traffic_light

class YOLO11Detector:
    def __init__(self, model_path=YOLO_MODEL_PATH):
        # Check for ONNX model first for CPU acceleration
        onnx_path = model_path.replace('.pt', '.onnx')
        if os.path.exists(onnx_path):
            print(f"[INIT] Found ONNX model: {onnx_path}. Using ONNX Runtime acceleration.")
            self.model = YOLO(onnx_path, task='detect')
        else:
            print(f"[INIT] Loading YOLO model from {model_path} (PyTorch)...")
            self.model = YOLO(model_path, task='detect')
            
        self.target_classes = set(TARGET_CLASSES)
        
    def detect(self, frame):
        """
        Run detection on the frame.
        
        Args:
            frame (numpy.ndarray): Input frame.
            
        Returns:
            list: List of detections. Each detection is a dict:
                  {'box': [x1, y1, x2, y2], 'class_id': int, 'conf': float, 'tl_color': str|None}
        """
        import config
        imgsz = getattr(config, 'YOLO_INFERENCE_SIZE', 320)
        results = self.model(frame, verbose=False, conf=CONF_THRESHOLD, imgsz=imgsz)
        detections = []
        
        for result in results:
            boxes = result.boxes
            for box in boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                
                if cls_id in self.target_classes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    
                    detection = {
                        'box': [x1, y1, x2, y2],
                        'class_id': cls_id,
                        'conf': conf,
                        'tl_color': None
                    }
                    
                    # Special handling for Traffic Light (Class ID 9)
                    if cls_id == 9:
                        # Ensure coordinates are within frame bounds
                        y1_c, y2_c = max(0, y1), min(frame.shape[0], y2)
                        x1_c, x2_c = max(0, x1), min(frame.shape[1], x2)
                        
                        crop = frame[y1_c:y2_c, x1_c:x2_c]
                        if crop.size > 0:
                            # Analyze color
                            detection['tl_color'] = analyze_traffic_light(crop)
                            # print(f"[DEBUG] Traffic Light Detected: {detection['tl_color']}")

                    detections.append(detection)
                    
        return detections
