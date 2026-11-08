import time
import config
from config import WARNING_COOLDOWN, CLASS_NAMES_CN

class WarningSystem:
    def __init__(self):
        # Store cooldowns per class to prevent one object from silencing others
        self.last_warning_times = {} 
        self.cooldown = WARNING_COOLDOWN
        
    def check_collision_risk(self, box_area, frame_area, class_id):
        """
        Check if the object poses a collision risk based on area.
        """
        if frame_area == 0:
            return False
            
        ratio = box_area / frame_area
        
        # Traffic Light (ID 9) needs a much smaller threshold since it's far away
        # Dynamic access to config to allow runtime updates from Web UI
        threshold = config.TRAFFIC_LIGHT_AREA_THRESHOLD if class_id == 9 else config.WARNING_AREA_THRESHOLD
        
        # print(f"[DEBUG] Class: {class_id}, Ratio: {ratio:.4f}, Thresh: {threshold}") # Debug info
        
        if ratio > threshold:
            return True
            
        return False

    def generate_warning_message(self, risks):
        """
        Generate a warning message for the user.
        
        Args:
            risks (list): List of tuples (class_id, ratio, extra_info).
            
        Returns:
            str: Warning message or None if cooled down.
        """
        current_time = time.time()
        
        if not risks:
            return None
            
        # Define priority weights (Higher number = Higher priority)
        # 1: Person (common, lower specific priority)
        # 2: Vehicles (Dangerous, important to identify)
        # 3: Traffic Light (Critical navigation info)
        priority_map = {
            0: 1, # Person
            1: 2, # Bicycle
            2: 2, # Car
            3: 2, # Motorcycle
            5: 2, # Bus
            7: 2, # Truck
            9: 3  # Traffic Light
        }
        
        # Sort risks by: 
        # 1. Custom Priority
        # 2. Size (Ratio)
        risks.sort(key=lambda x: (priority_map.get(x[0], 1), x[1]), reverse=True)
        
        for class_id, ratio, extra_info in risks:
            last_time = self.last_warning_times.get(class_id, 0)
            
            if current_time - last_time > self.cooldown:
                self.last_warning_times[class_id] = current_time
                
                # Custom Messages for Traffic Light
                if class_id == 9:
                    if extra_info == 'Red':
                        return "红灯，请停止等待"
                    elif extra_info == 'Green':
                        return "绿灯，请起步通行"
                    else:
                        return "前方发现红绿灯"
                
                # Default Logic
                class_name = CLASS_NAMES_CN.get(class_id, "障碍物")
                return f"警告！前方有{class_name}，请注意绕行"
                
        return None
