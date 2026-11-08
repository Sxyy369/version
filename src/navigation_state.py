import time
from enum import Enum, auto
import config
from config import CLASS_NAMES_CN

class NavigationMode(Enum):
    NORMAL = auto()
    CROSSING_STREET = auto()
    BLIND_PATH = auto()

class CrosswalkState(Enum):
    CRUISE = auto()      # State 0: Normal Cruise
    OBSERVING = auto()   # State 1: Intersection Observation
    RED_WAIT = auto()    # State 2: Red Light Wait
    GREEN_CHECK = auto() # State 3: Green Light Check & Crossing

class CrosswalkStateMachine:
    def __init__(self):
        self.state = CrosswalkState.CRUISE
        self.state_enter_time = time.time()
        self.last_tl_state = "Unknown"
        self.tl_stable_frames = 0
        self.required_stable_frames = 3 # Require 3 consecutive frames of same color to confirm
        self.crossing_safe_frames = 0

    def reset_state(self):
        self.state = CrosswalkState.CRUISE
        self.state_enter_time = time.time()
        self.last_tl_state = "Unknown"
        self.tl_stable_frames = 0
        self.crossing_safe_frames = 0
        return None

    def update(self, detections, frame_width, frame_height):
        """
        Engineers the state machine logic based on detections.
        Returns a tuple: (Warning Message String or None, Priority Rank 0-3)
        Priority: 0=Highest (Danger), 3=Info
        """
        current_time = time.time()
        time_in_state = current_time - self.state_enter_time

        # 1. Parsing Detections
        has_crosswalk = False
        tl_color = "Unknown"
        crossing_vehicles = []
        
        # Central horizontal zone for "in-path" checking (e.g. 30% to 70% of width)
        safe_zone_left = frame_width * 0.3
        safe_zone_right = frame_width * 0.7

        for det in detections:
            cls_id = det['class_id']
            # Assuming 8 is crosswalk/zebra crossing in your YOLO classes, adjust if needed
            # We fallback to traffic light triggering it if crosswalk ID isn't standard
            if cls_id == 8 or cls_id == 9: 
                has_crosswalk = True
            
            if cls_id == 9: # Traffic Light
                color = det.get('tl_color', 'Unknown')
                if color != "Unknown":
                    if color == self.last_tl_state:
                        self.tl_stable_frames += 1
                    else:
                        self.tl_stable_frames = 0
                        self.last_tl_state = color
                    
                    # Only accept color if stable
                    if self.tl_stable_frames >= self.required_stable_frames:
                        tl_color = color

            # Check for vehicles (Car:2, Bus:5, Truck:7, Bicycle:1, Motorcycle:3)
            # and verify if they are horizontally crossing the center path
            if cls_id in [1, 2, 3, 5, 7]:
                x1, y1, x2, y2 = det['box']
                cx = (x1 + x2) / 2
                # If vehicle center is roughly in our path or moving through it
                if safe_zone_left < cx < safe_zone_right:
                    crossing_vehicles.append(cls_id)

        # 2. State Machine Logic
        msg = None
        priority = 3

        if self.state == CrosswalkState.CRUISE:
            if has_crosswalk:
                self.state = CrosswalkState.OBSERVING
                self.state_enter_time = current_time
                msg = "前方发现十字路口，请减速慢行，正在为您检测红绿灯..."
                priority = 1
                
        elif self.state == CrosswalkState.OBSERVING:
            if tl_color == "Red":
                self.state = CrosswalkState.RED_WAIT
                self.state_enter_time = current_time
                msg = "当前是红灯，请停止等待。"
                priority = 0 # High Priority
            elif tl_color == "Green":
                self.state = CrosswalkState.GREEN_CHECK
                self.state_enter_time = current_time
                msg = "前方绿灯，正在确认车辆路况..."
                priority = 1
            elif time_in_state > 5.0:
                # Timeout observing
                msg = "未明确识别红绿灯，请谨慎自主判断路况"
                priority = 0
                self.reset_state()

        elif self.state == CrosswalkState.RED_WAIT:
            # We don't timeout red light wait easily, people wait minutes
            if tl_color == "Green":
                self.state = CrosswalkState.GREEN_CHECK
                self.state_enter_time = current_time
                msg = "绿灯亮起。请起步通行，请注意倾听可能出现的转弯车辆。"
                priority = 0

        elif self.state == CrosswalkState.GREEN_CHECK:
            if len(crossing_vehicles) > 0:
                self.crossing_safe_frames = 0
                # Throttle this message so it doesn't spam every frame
                if int(time_in_state*10) % 20 == 0: # roughly every 2 seconds
                    msg = "绿灯，但前方有车辆横穿，请暂时停止等待。"
                    priority = 0
            else:
                self.crossing_safe_frames += 1
                if self.crossing_safe_frames > 5: # 5 frames safe
                    msg = "前方无阻挡，可以安全起步通行。"
                    priority = 0
                    self.reset_state() # Reset after successful cross command

            # Failsafe: Light turned red while checking
            if tl_color == "Red":
                 msg = "注意！红绿灯变红，请停止等待！"
                 priority = 0
                 self.state = CrosswalkState.RED_WAIT

        return msg, priority
