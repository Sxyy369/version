import math
import time

class SensorFusion:
    def __init__(self, step_length=0.6):
        """
        传感器融合模块：结合低频 GPS（如来自手机）和高频 IMU（模拟步伐推算）。
        :param step_length: 每步的平均长度（单位：米）
        """
        self.step_length = step_length
        self.current_lat = None
        self.current_lon = None
        
        self.last_gps_time = 0
        self.heading = 0.0 # 当前面朝角度 (0-360)
        
        # 地球半径（米）
        self.R = 6378137.0

    def update_gps(self, lat, lon, hdop=1.0):
        """
        接收真实的低频 GPS 数据更新。
        在真实场景中，如果 HDOP（水平精度因子）很大，可以降低权重甚至忽略。
        """
        self.current_lat = float(lat)
        self.current_lon = float(lon)
        self.last_gps_time = time.time()
        # print(f"[FUSION] GPS Anchor Received: ({self.current_lat:.6f}, {self.current_lon:.6f})")

    def update_heading(self, heading):
        """
        更新用户的面部朝向（来自 IMU 陀螺仪或地磁计）。
        """
        self.heading = float(heading)

    def on_step_detected(self):
        """
        IMU 触发：检测到用户卖出了一步（高频）。
        调用此方法将使用当前的 heading 和 step_length 向前推算 0.6 米的新坐标。
        如果当前没有基准 GPS 坐标，则无法推算。
        """
        if self.current_lat is None or self.current_lon is None:
            return False
            
        # 根据当前朝向，将距离分解为经度和纬度的偏移量
        # 北纬度 (dy)
        dy = self.step_length * math.cos(math.radians(self.heading))
        # 东经度 (dx)
        dx = self.step_length * math.sin(math.radians(self.heading))
        
        # 将偏移量 (米) 转换为经纬度度数
        # 纬度 1度 约等于 111132 米
        delta_lat = dy / 111132.0
        
        # 经度 1度 的距离在不同纬度下是不同的，约等于 111132 * cos(lat)
        delta_lon = dx / (111132.0 * math.cos(math.radians(self.current_lat)))
        
        self.current_lat += delta_lat
        self.current_lon += delta_lon
        
        # print(f"[FUSION] Step PDR (+0.6m @ {self.heading}°): ({self.current_lat:.6f}, {self.current_lon:.6f})")
        return True

    def get_fused_location_str(self):
        """
        获取当前融合推算后的位置字符串，格式适用于高德 API (lon,lat)
        """
        if self.current_lat is None or self.current_lon is None:
            return None
        return f"{self.current_lon:.6f},{self.current_lat:.6f}"

# 模拟 IMU 处理器（用于测试）
class MockIMU:
    def __init__(self, fusion_engine):
        self.fusion = fusion_engine
        
    def simulate_walking(self, steps=5, heading=0, delay=0.5):
        """
        模拟行走
        """
        self.fusion.update_heading(heading)
        for i in range(steps):
            self.fusion.on_step_detected()
            time.sleep(delay)
