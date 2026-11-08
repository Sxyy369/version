import requests
import json
import time

class GeoNavigator:
    def __init__(self, api_key=None, gps_callback=None):
        self.api_key = api_key
        self.gps_callback = gps_callback
        # Highde (Gaode) Map API Base URL
        self.base_url = "https://restapi.amap.com/v3"
        self.simulating = api_key is None or api_key == "YOUR_AMAP_KEY"
        
        if self.simulating:
            print("[NAV] No API Key provided. Running in SIMULATION MODE.")
            
        self.current_step_index = 0
        self.steps = []
        self.is_navigating = False
        self.destination = ""

    def get_regeo_address(self, coords):
        """Get formatted address from coords"""
        if self.simulating: return "模拟位置(ReGeo)"
        
        url = f"{self.base_url}/geocode/regeo"
        params = {
            "key": self.api_key,
            "location": coords,
            "output": "json",
            "extensions": "base"
        }
        try:
            response = requests.get(url, params=params, timeout=3)
            data = response.json()
            if data["status"] == "1":
                return data["regeocode"]["formatted_address"]
        except:
            pass
        return None

    def get_current_location(self):
        """
        Get current location using IP Positioning API or Phone GPS.
        Returns: (coords_str, description_str) or None
        """
        # 1. Try GPS from Phone
        if self.gps_callback:
            gps_data = self.gps_callback()
            if gps_data and 'lon' in gps_data and 'lat' in gps_data:
                lon = gps_data['lon']
                lat = gps_data['lat']
                acc = gps_data.get('acc', 0)
                coords = f"{lon},{lat}"
                
                # Get Readable Address
                address = self.get_regeo_address(coords)
                
                # Append accuracy warning if signal is weak (>50m)
                if acc > 50:
                    acc_str = f"，定位偏差约{int(acc)}米"
                    if address:
                        address += acc_str
                    else:
                        address = f"手机GPS位置{acc_str}"
                elif not address:
                    address = f"手机GPS位置(精度{int(acc)}米)"
                
                print(f"[NAV] Using Phone GPS: {coords} -> {address}")
                return coords, address

        if self.simulating:
            return "116.397428,39.90923", "模拟位置(天安门)"

        url = f"{self.base_url}/ip"
        params = {"key": self.api_key, "output": "json"}
        try:
            # Note: This returns location of the valid external IP
            response = requests.get(url, params=params, timeout=3)
            data = response.json()
            if data["status"] == "1":
                # Get Description
                city = data.get("city", "")
                province = data.get("province", "")
                if isinstance(city, list): city = "" # Sometimes API returns [] for empty
                if isinstance(province, list): province = ""
                desc = f"{province}{city}"
                
                # Get Coords
                if "rectangle" in data:
                    rect = data["rectangle"]
                    if isinstance(rect, str) and ";" in rect:
                        p1, p2 = rect.split(";")
                        return p1, desc
                    elif isinstance(rect, str) and "," in rect: # Single point?
                        return rect, desc
                        
                # Fallback to 'location' field if present (rare for IP)
                if "location" in data and isinstance(data["location"], str):
                     return data["location"], desc
                     
        except Exception as e:
            print(f"[NAV ERROR] IP Location failed: {e}")
        return None

    def search_place(self, query, city="", curr_location=None):
        """
        Search for a place using keywords.
        curr_location: "lon,lat" optional, for distance sorting
        Returns: (name, location_str) or None
        """
        if self.simulating:
             print(f"[NAV SIM] Searching for {query}...")
             if "fail" in query: return None # test failure
             return f"{query}(模拟)", "116.397428,39.91923" 

        url = f"{self.base_url}/place/text"
        params = {
            "key": self.api_key,
            "keywords": query,
            "city": city, # Empty means nationwide
            "output": "json",
            "offset": 1, # Only need top 1
            "page": 1
        }
        
        # Location Bias (Distance Sort)
        if curr_location:
            params["location"] = curr_location
            params["sortrule"] = "distance"
            print(f"[NAV DEBUG] Search '{query}' near {curr_location}")

        try:
            # DEBUG
            # print(f"[NAV DEBUG] GET {url} params={params}")
            response = requests.get(url, params=params, timeout=5)
            data = response.json()
            if data["status"] == "1" and data["pois"]:
                poi = data["pois"][0]
                print(f"[NAV DEBUG] Found: {poi['name']} at {poi['location']}")
                return poi["name"], poi["location"]
            else:
                print(f"[NAV DEBUG] Search Failed. Response: {data}")
        except Exception as e:
            print(f"[NAV ERROR] Search failed: {e}")
        return None
    def get_city_from_coords(self, coords):
        """
        Reverse geocode to get city name/code for transit navigation.
        coords: "lon,lat"
        """
        if self.simulating: return "北京市"
        
        url = f"{self.base_url}/geocode/regeo"
        params = {
            "key": self.api_key,
            "location": coords,
            "output": "json",
            "extensions": "base"
        }
        try:
            response = requests.get(url, params=params, timeout=3)
            data = response.json()
            if data["status"] == "1":
                return data["regeocode"]["addressComponent"]["city"]
        except:
            pass
        return None

    def start_navigation(self, start_pos, end_pos, end_name="终点", mode="walking"):
        """
        Start navigation from start_pos to end_pos.
        mode: "walking", "driving", "transit"
        """
        self.destination = end_name
        self.current_step_index = 0
        self.steps = []
        self.is_navigating = False
        
        mode_str = "驾车" if mode == "driving" else "步行" if mode == "walking" else "公交"

        if self.simulating:
            print(f"[NAV SIM] Calculating {mode} route to {end_name}...")
            self.is_navigating = True
            return True, f"模拟{mode_str}导航开始，前往{end_name}。请说“下一步”听取指引。"

        # Select API based on mode
        url = ""
        params = {
            "key": self.api_key,
            "origin": start_pos,
            "destination": end_pos,
            "output": "json"
        }
        
        if mode == "driving":
            url = f"{self.base_url}/direction/driving"
            params["strategy"] = 0 # speed first
        elif mode == "transit":
            url = f"{self.base_url}/direction/transit/integrated"
            # Transit needs city!
            city = self.get_city_from_coords(start_pos)
            if not city:
                 return False, "公交导航需要获取城市信息失败，请稍后再试。"
            params["city"] = city
            params["strategy"] = 0 # speed first
        else: # walking
            url = f"{self.base_url}/direction/walking"

        print(f"[NAV] Requesting {mode} route: {start_pos} -> {end_pos}")
        
        try:
            response = requests.get(url, params=params, timeout=5)
            data = response.json()
            
            if data["status"] == "1":
                # Check for "count" or "route"
                if "route" not in data:
                     return False, f"未找到{mode_str}路线。"
                
                route = data["route"]
                
                # Parsing Logic
                if mode == "transit":
                     if not route.get("transits"):
                         return False, "未找到合适的公交路线。"
                     
                     # Take first transit option
                     transit_route = route["transits"][0]
                     distance = transit_route.get("distance", 0)
                     duration = transit_route.get("duration", 0)
                     
                     self.steps = []
                     # Transit segments are complex (walking + bus + subway)
                     # We flatten them into simple steps
                     if "segments" in transit_route:
                         for seg in transit_route["segments"]:
                             if "bus" in seg and seg["bus"]["buslines"]:
                                 line = seg["bus"]["buslines"][0]["name"]
                                 self.steps.append({"instruction": f"乘坐 {line}"})
                             elif "walking" in seg and seg["walking"]:
                                 dist = seg["walking"]["distance"]
                                 self.steps.append({"instruction": f"步行 {dist}米"})
                     
                else: # Walking / Driving
                    if not route["paths"]:
                         return False, f"未找到{mode_str}路线。"
                    path = route["paths"][0]
                    self.steps = path["steps"]
                    distance = path.get("distance", "0")
                    duration = path.get("duration", "0")
                
                self.is_navigating = True
                
                # Human readable duration
                mins = int(duration) // 60
                time_str = f"{mins}分钟" if mins < 60 else f"{mins//60}小时{mins%60}分钟"
                
                # First Step preview for transit
                first_instr = ""
                if mode == "transit" and self.steps:
                    first_instr = f"首先，{self.steps[0]['instruction']}。"

                return True, f"已规划{mode_str}路线到{end_name}。全程{distance}米，预计耗时{time_str}。{first_instr}请说“下一步”听取指引。"
            else:
                err_info = data.get("info", "未知错误")
                return False, f"路线规划失败: {err_info}"
        except Exception as e:
            return False, f"导航请求失败: {str(e)}"

    def get_current_instruction(self):
        """Get current step instruction without advancing"""
        if not self.is_navigating or not self.steps:
            return None
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]["instruction"]
        return "导航结束"

    def next_step(self):
        """Advance to next step and return instruction"""
        if not self.is_navigating: return "未在导航中"
        
        # If we successfully started, current_index is 0. 
        # But we haven't read it yet maybe?
        # Let's say next_step reads current, then increments? 
        # Or increments then reads?
        # Usually "Next" means read the one I haven't heard.
        # But if index=0 and we just started, "Next" should read step 0.
        # So we create a flag? Or just use index logic.
        
        if self.current_step_index < len(self.steps):
            instr = self.steps[self.current_step_index]["instruction"]
            self.current_step_index += 1
            return instr
        else:
            self.is_navigating = False
            return "导航结束，已到达目的地。"

    def prev_step(self):
        """Go back one step"""
        if not self.is_navigating: return "未在导航中"
        if self.current_step_index > 0:
            self.current_step_index -= 1
            # When going back, we want to hear the one we stepped back to.
            # But wait, next_step increments AFTER reading.
            # So if we are at index 1 (meaning we finished 0), 
            # prev_step should take us to 0, and we read 0.
            # But the logic above: read i, then i++.
            # So to read i-1, we set i = i-1.
            return self.steps[self.current_step_index]["instruction"]
        return "已经是第一步了"

    def repeat_step(self):
        """Repeat current step (which is actually index-1 since we incremented)"""
        if not self.is_navigating: return "未在导航中"
        
        # If we haven't started (index=0), read index 0 (preview)
        if self.current_step_index == 0:
             return self.steps[0]["instruction"]
             
        # If we are at index i, it means we just finished reading i-1.
        if self.current_step_index > 0:
            return self.steps[self.current_step_index - 1]["instruction"]
            
        return None

    # LEGACY COMPATIBILITY
    def get_next_guidance(self):
        return None # Disable auto-advance
