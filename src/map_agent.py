import requests
import json
import math
import time
from datetime import datetime

class MapAgent:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://restapi.amap.com/v3"
        self.current_route = None
        self.current_step_index = 0
        self.last_instruction = ""
        self.is_approaching_intersection = False
        
        # POI Logic
        self.announced_pois = set()
        self.last_poi_time = 0
        
        print(f"[MAP] Initialized with Key: {api_key[:6]}******")

    def reverse_geocode(self, location_str):
        """
        Convert lon,lat to a readable address/POI name.
        """
        url = f"{self.base_url}/geocode/regeo"
        params = {
            "key": self.api_key,
            "location": location_str,
            "extensions": "all",
            "radius": 100
        }
        try:
            response = requests.get(url, params=params, timeout=3)
            data = response.json()
            if data["status"] == "1":
                regeq = data.get("regeocode", {})
                # Try to get the most specific POI or street
                pois = regeq.get("pois", [])
                if pois:
                    return pois[0].get("name", "")
                roads = regeq.get("roads", [])
                if roads:
                    return roads[0].get("name", "")
                
                # Fallback to formatted address
                return regeq.get("formatted_address", "未知位置")
        except Exception as e:
            print(f"[MAP] ReGeo Error: {e}")
        return "当前位置"

    def _sanitize_instruction(self, instruction):
        """
        Translate absolute compass directions to semantic/relative directions for blind users.
        Example: "向东步行100米向左转" -> "正前方步行100米向左转"
        """
        import re
        # Replace "向东/南/西/北(偏东/南/西/北)步行" with "正前方步行"
        instruction = re.sub(r'向[东西南北]+(偏[东西南北]+)?步行', '正前方步行', instruction)
        # Remove remaining "向东/南/西/北" if it's just describing a turn angle, to avoid compass confusion
        instruction = re.sub(r'向[东西南北]+(偏[东西南北]+)?', '向前方', instruction)
        return instruction

    def search_location(self, keyword, city="beijing"):
        """
        Search for a location by keyword.
        Returns: (name, location_str) or None
        """
        url = f"{self.base_url}/place/text"
        params = {
            "key": self.api_key,
            "keywords": keyword,
            "city": city,
            "children": 1,
            "offset": 1,
            "page": 1,
            "extensions": "all"
        }
        
        try:
            response = requests.get(url, params=params, timeout=5)
            data = response.json()
            
            if data["status"] == "1" and int(data["count"]) > 0:
                poi = data["pois"][0]
                name = poi["name"]
                location = poi["location"]
                print(f"[MAP] Found: {name} at {location}")
                return name, location
            else:
                print(f"[MAP] Search failed: {data.get('info', 'Unknown error')}")
                return None
        except Exception as e:
            print(f"[MAP] Search Error: {e}")
            return None

    def get_custom_route(self, origin, destination, mode="walking"):
        """
        Get route from origin (lon,lat) to destination (lon,lat) based on selected mode.
        Supported modes: walking, transit
        """
        self.current_destination = destination
        self.nav_steps = []
        self.current_step_index = 0
        self.current_route = None
        self.has_started = False
        self.last_dev_time = 0
        self.last_cruise_time = 0

        if mode == "transit":
            # Transit routing requires city. Using '010' (Beijing) or nearby city as default.
            # In real-world, reverse geocoding origin gives exact city. We'll use default 'beijing' for now.
            url = f"{self.base_url}/direction/transit/integrated"
            params = {
                "key": self.api_key,
                "origin": origin,
                "destination": destination,
                "city": "北京", # Auto-fallback required for transit API
                "strategy": 0,
                "nightflag": 0
            }
            try:
                print(f"[MAP] Trying route mode: transit...")
                response = requests.get(url, params=params, timeout=5)
                data = response.json()
                
                if data.get("status") == "1" and int(data.get("count", 0)) > 0:
                    transits = data.get("route", {}).get("transits", [])
                    if transits:
                        route = transits[0] # Take first transit option
                        self.current_route = route
                        
                        segments = route.get("segments", [])
                        total_dist = route.get("distance", "0")
                        duration = int(route.get("duration", "0")) // 60
                        
                        # Process segments flattening into steps
                        for seg in segments:
                            # 1. Walking part of segment
                            walking = seg.get("walking")
                            if walking and walking.get("steps"):
                                for w_step in walking["steps"]:
                                    self.nav_steps.append({
                                        "instruction": self._sanitize_instruction(w_step["instruction"]),
                                        "road": w_step.get("road", ""),
                                        "distance": int(w_step["distance"]),
                                        "action": w_step.get("action", ""),
                                        "polyline": w_step["polyline"]
                                    })
                            # 2. Bus/Subway part of segment
                            bus = seg.get("bus", {}).get("buslines", [])
                            if bus:
                                main_bus = bus[0] # Take primary line
                                bus_name = main_bus.get("name", "").split('(')[0]
                                dep_stop = main_bus.get("departure_stop", {}).get("name", "")
                                arr_stop = main_bus.get("arrival_stop", {}).get("name", "")
                                via_num = main_bus.get("via_num", 0)
                                polyline = main_bus.get("polyline", "")
                                
                                instruction = f"在 {dep_stop} 乘坐 {bus_name}, 经过 {via_num} 站后在 {arr_stop} 下车"
                                self.nav_steps.append({
                                    "instruction": instruction,
                                    "road": bus_name,
                                    "distance": int(main_bus.get("distance", 0)),
                                    "action": "乘坐公交",
                                    "polyline": polyline
                                })
                        
                        start_name = self.reverse_geocode(origin)
                        return f"您当前在 {start_name}，准备前往目的地。公交地铁路线已规划，预计用时{duration}分钟。"
                print(f"[MAP] Transit route failed: {data.get('info')}")
            except Exception as e:
                print(f"[MAP] Transit Route Error: {e}")
                
            # If transit fails, fallback to walking
            print("[MAP] transit failed or no routes found, falling back to walking")
            mode = "walking"

        # Walking mode (default or fallback)
        if mode == "walking":
            url = f"{self.base_url}/direction/walking"
            params = {
                "key": self.api_key,
                "origin": origin,
                "destination": destination,
            }
            try:
                print(f"[MAP] Trying route mode: walking...")
                response = requests.get(url, params=params, timeout=5)
                data = response.json()
                
                if data.get("status") == "1" and int(data.get("count", 0)) > 0:
                    route = data["route"]["paths"][0]
                    self.current_route = route
                    steps = route["steps"]
                    total_dist = route["distance"]
                    
                    for step in steps:
                        self.nav_steps.append({
                            "instruction": self._sanitize_instruction(step["instruction"]),
                            "road": step.get("road", ""),
                            "distance": int(step["distance"]),
                            "action": step.get("action", ""),
                            "polyline": step["polyline"]
                        })
                    
                    dist_val = int(total_dist)
                    dist_str = f"{dist_val//1000}公里{dist_val%1000}米" if dist_val >= 1000 else f"{dist_val}米"
                    start_name = self.reverse_geocode(origin)
                    return f"您当前在 {start_name}，准备前往目的地。步行路线规划成功，全程 {dist_str}。"
                print(f"[MAP] Walking route failed: {data.get('info')}")
            except Exception as e:
                print(f"[MAP] Route Error (walking): {e}")

        return "规划失败，距离过远或网络异常"

    def search_nearby_poi(self, current_location_str):
        """
        Search for nearby POIs to use as environmental reference points.
        Uses whitelist filtering for specific visually significant types:
        - Banks (160100)
        - Convenience Stores (060101)
        - Fast Food (050300)
        - Subways (150500)
        - Bus Stations (150700)
        - Toilets (200300)
        - Gates/Entrances (190301)
        """
        # Cool down of 30 seconds
        if time.time() - self.last_poi_time < 30:
            return None
            
        url = f"{self.base_url}/place/around"
        params = {
            "key": self.api_key,
            "location": current_location_str,
            "radius": 50, # Increased radius to 50m for better chances
            # Added more types: supermarkets (060400), hospitals (090100)
            "types": "160100|060101|050300|150500|150700|200300|190301|060400|090100",
            "sortrule": "distance",
            "offset": 1,
            "page": 1,
            "extensions": "base"
        }
        
        try:
            response = requests.get(url, params=params, timeout=3)
            data = response.json()
            
            if data["status"] == "1" and int(data.get("count", 0)) > 0:
                poi = data["pois"][0]
                poi_id = poi["id"]
                name = poi["name"]
                
                # Check if already announced
                if poi_id in self.announced_pois:
                    return None
                    
                self.announced_pois.add(poi_id)
                self.last_poi_time = time.time()
                
                print(f"[MAP] Emitting POI Environment Context: {name}")
                return name
                
        except Exception as e:
            print(f"[MAP] POI Search Error: {e}")
            
        return None

    def get_navigation_guidance(self, current_location_str, heading=None):
        """
        Check current location against route and return guidance.
        Input: "lon,lat" string (GCJ-02), and optional 'heading' (0-360 degrees, 0=North)
        Uses advanced map-matching with anticipatory snapping for smoother turn transitions,
        and generates clock-direction semantics based on the user's heading.
        """
        if not self.current_route or not self.nav_steps:
            return None

        try:
            curr_lon, curr_lat = map(float, current_location_str.split(','))
            
            # Safety checks
            if self.current_step_index >= len(self.nav_steps):
                return None
            
            step = self.nav_steps[self.current_step_index]
            
            # --- 场景一：起步与方向找寻 ---
            if not getattr(self, 'has_started', False):
                self.has_started = True
                if heading is not None and step["polyline"]:
                    next_pts = step["polyline"].split(';')
                    if len(next_pts) > 1:
                        lon1, lat1 = map(float, next_pts[0].split(','))
                        lon2, lat2 = map(float, next_pts[1].split(','))
                        bearing = self._calculate_bearing(lat1, lon1, lat2, lon2)
                        clock_dir = self._get_clock_direction(bearing, heading)
                        return f"导航开始。请转向您的{clock_dir}点钟方向，顺着脚下的盲道，前方直行{step['distance']}米。"
                return f"导航开始。请顺着脚下的盲道，{self._sanitize_instruction(step['instruction'])}。"
            
            # Parse polyline for the CURRENT step
            points = step["polyline"].split(';')
            parsed_points = []
            for pt in points:
                plon, plat = map(float, pt.split(','))
                parsed_points.append((plon, plat))
            
            # --- ★ Advanced Map Matching: 同时关注当前和下一段路 ---
            # 1. 计算当前段的吸附
            snapped_lon, snapped_lat, min_dist = self._snap_to_polyline(
                curr_lon, curr_lat, parsed_points
            )

            # 2. 预判：如果还有下一步，计算下一步的吸附距离
            if self.current_step_index + 1 < len(self.nav_steps):
                next_step = self.nav_steps[self.current_step_index + 1]
                next_points = []
                for pt in next_step["polyline"].split(';'):
                    plon, plat = map(float, pt.split(','))
                    next_points.append((plon, plat))
                
                _, _, dist_to_next = self._snap_to_polyline(curr_lon, curr_lat, next_points)
                
                # 如果用户离下一段路明显更近（或者是正在进入下一段），且已经接近当前段终点
                end_lon, end_lat = parsed_points[-1]
                dist_to_turn_pt = self._haversine_distance(curr_lat, curr_lon, end_lat, end_lon)
                
                if dist_to_next < min_dist and dist_to_turn_pt < 30:
                    print(f"[MAP] Anticipatory transition triggered: DistNext({int(dist_to_next)}m) < DistCurr({int(min_dist)}m)")
                    self.current_step_index += 1
                    return self.get_navigation_guidance(current_location_str, heading) # 递归更新到新状态

            # --- 场景二：偏航检测与微调 ---
            if min_dist > 60: 
                print(f"[MAP] Off-route detected! Dist: {int(min_dist)}m")
                if hasattr(self, 'current_destination') and self.current_destination:
                    msg = self.get_custom_route(current_location_str, self.current_destination)
                    return f"您已偏航，正在为您重新规划路线。{msg}"
                else:
                    return "您已偏航，请回到正确路线上"

            elif min_dist > 8: # 轻微偏航，做微观纠正
                now = time.time()
                if not hasattr(self, 'last_dev_time'): self.last_dev_time = 0
                if now - self.last_dev_time > 15: # 冷却15秒
                    self.last_dev_time = now
                    if heading is not None:
                        bearing = self._calculate_bearing(curr_lat, curr_lon, snapped_lat, snapped_lon)
                        clock_dir = self._get_clock_direction(bearing, heading)
                        steps = max(1, int(min_dist / 0.6))
                        return f"注意，您已轻微偏离。请向转至{clock_dir}点钟方向，走约{steps}步即可回到主路线。"

            # --- 核心进度推进计算 ---
            end_lon, end_lat = parsed_points[-1]
            # 这里用吸附后的坐标计算到转弯点的距离
            dist_to_turn = self._haversine_distance(snapped_lat, snapped_lon, end_lat, end_lon)
            
            print(f"[MAP] Step {self.current_step_index+1}/{len(self.nav_steps)} DistToTurn: {int(dist_to_turn)}m -> {step['instruction']}")

            # Threshold to advance step: 18 meters -> changed to 5 meters for precision
            # Only advance to the NEXT instruction if we are practically AT the turn point (<5m)
            # Otherwise, during 5m~15m, give an exact countdown
            if dist_to_turn < 15:
                # Entering high-sensitivity zone!
                
                # --- 场景五：最后十米到达 ---
                if self.current_step_index == len(self.nav_steps) - 1 and dist_to_turn <= 15:
                    self.current_step_index += 1
                    clock_dir = 12
                    if heading is not None:
                        bearing = self._calculate_bearing(snapped_lat, snapped_lon, end_lat, end_lon)
                        clock_dir = self._get_clock_direction(bearing, heading)
                    poi_hint = self.search_nearby_poi(f"{end_lon},{end_lat}")
                    hint_str = f"附近有 {poi_hint}" if poi_hint else "您可以试着摸寻门禁或留意周边环境音"
                    return f"距离终点还有最后10米，就在您的{clock_dir}点钟方向。{hint_str}。本次导航圆满结束。"

                if dist_to_turn < 5:
                    # We have reached the turn
                    self.current_step_index += 1
                    if self.current_step_index >= len(self.nav_steps):
                        return None
                    else:
                        next_step = self.nav_steps[self.current_step_index]
                        nav_msg = f"{step['action'] if step.get('action') else '前方'}，{next_step['instruction']}"
                        
                        if heading is not None and next_step["polyline"]:
                            next_pts = next_step["polyline"].split(';')
                            if next_pts:
                                n_lon, n_lat = map(float, next_pts[0].split(','))
                                bearing = self._calculate_bearing(snapped_lat, snapped_lon, n_lat, n_lon)
                                clock_dir = self._get_clock_direction(bearing, heading)
                                nav_msg = f"立即转向 {clock_dir} 点钟方向"
                                
                        return nav_msg
                else:
                    # Countdown zone (5m ~ 15m)
                    next_step = self.nav_steps[self.current_step_index + 1] if self.current_step_index + 1 < len(self.nav_steps) else None
                    if heading is not None and next_step and next_step["polyline"]:
                        next_pts = next_step["polyline"].split(';')
                        if next_pts:
                            n_lon, n_lat = map(float, next_pts[0].split(','))
                            bearing = self._calculate_bearing(snapped_lat, snapped_lon, n_lat, n_lon)
                            clock_dir = self._get_clock_direction(bearing, heading)
                            
                            # CLOUD LOGIC: Check if next instruction implies an intersection
                            if "转" in next_step['instruction'] or "路口" in next_step['instruction'] or "红绿灯" in next_step['instruction']:
                                self.is_approaching_intersection = True
                            else:
                                self.is_approaching_intersection = False
                                
                            next_inst = self._sanitize_instruction(next_step['instruction'])
                            base_msg = f"正前方步行约 {int(dist_to_turn)} 米，然后 {next_inst}"
                            poi_name = self.search_nearby_poi(f"{snapped_lon},{snapped_lat}")
                            if poi_name:
                                return f"{base_msg}，即将路过 {poi_name}"
                            return base_msg
                    
                    self.is_approaching_intersection = False
                    return None
            
            # --- 场景二：长直行巡航路段防迷失 ---
            self.is_approaching_intersection = False
            
            if dist_to_turn > 50:
                now = time.time()
                if not hasattr(self, 'last_cruise_time'): self.last_cruise_time = 0
                if now - self.last_cruise_time > 45: # 45秒冷却
                    self.last_cruise_time = now
                    poi_name = self.search_nearby_poi(f"{snapped_lon},{snapped_lat}")
                    base_msg = f"沿当前盲道继续直行{int(dist_to_turn)}米，请留意倾听周围环境音保持笔直"
                    if poi_name:
                         return f"{base_msg}，您正经过 {poi_name}"
                    return base_msg
                 
            return None

        except Exception as e:
            print(f"[MAP] Guidance Error: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _snap_to_polyline(self, lon, lat, polyline_points):
        """
        将点投影到线段集合上。改进：如果点在线段延长线上，限制在端点。
        """
        min_dist = float('inf')
        best_lon, best_lat = lon, lat
        
        if not polyline_points:
            return lon, lat, 9999
            
        for i in range(len(polyline_points) - 1):
            p1 = polyline_points[i]
            p2 = polyline_points[i+1]
            
            # 计算投影
            cur_lon, cur_lat, d = self._project_point_to_segment(lon, lat, p1, p2)
            if d < min_dist:
                min_dist = d
                best_lon, best_lat = cur_lon, cur_lat
                
        return best_lon, best_lat, min_dist

    def _project_point_to_segment(self, px, py, p1, p2):
        """
        计算点 (px, py) 到线段 p1-p2 的最短距离及投影点。
        使用平面坐标近似（适合短距离）。
        """
        x1, y1 = p1
        x2, y2 = p2
        
        dx = x2 - x1
        dy = y2 - y1
        
        if dx == 0 and dy == 0:
            return x1, y1, self._haversine_distance(py, px, y1, x1)
            
        # 投影参数 t
        t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
        t = max(0, min(1, t)) # 限制在线段内
        
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy
        
        dist = self._haversine_distance(py, px, proj_y, proj_x)
        return proj_x, proj_y, dist

    def _haversine_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance in meters between two points"""
        R = 6371000 # Earth radius
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2) * (math.sin(dlambda/2)**2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c

    def _calculate_bearing(self, lat1, lon1, lat2, lon2):
        """
        计算从点1到点2的真北方位角 (Bearing)
        返回 0-360 度的角度 (0 = 正北, 90 = 正东)
        """
        lat1 = math.radians(lat1)
        lat2 = math.radians(lat2)
        diff_lon = math.radians(lon2 - lon1)

        x = math.sin(diff_lon) * math.cos(lat2)
        y = math.cos(lat1) * math.sin(lat2) - (math.sin(lat1) * math.cos(lat2) * math.cos(diff_lon))

        initial_bearing = math.atan2(x, y)
        initial_bearing = math.degrees(initial_bearing)
        bearing = (initial_bearing + 360) % 360
        return bearing

    def _get_clock_direction(self, bearing, current_heading):
        """
        结合目标方位角 (bearing) 和当前用户朝向 (heading)，转化为对应的时钟方向。
        :param bearing: 目标点到正北的角度 (0-360)
        :param current_heading: 用户当前面部朝向到正北的角度 (0-360)
        :return: 1-12 的时钟整点数字
        """
        # 计算相对角度 (-180 到 180)
        relative_angle = (bearing - current_heading + 360) % 360
        if relative_angle > 180:
            relative_angle -= 360
            
        # 映射到 12 个时钟区间 (每个区间 30 度)
        # 12点: -15 到 15
        # 1点: 15 到 45
        # 2点: 45 到 75
        # ... 以此类推
        clock_value = round(relative_angle / 30.0)
        
        # 将 0 转换为 12点
        if clock_value <= 0:
            clock_value += 12
            
        return clock_value
