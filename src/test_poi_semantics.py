import sys
import os
import time

# Ensure the src directory is in the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.map_agent import MapAgent
from config import AMAP_API_KEY

def test_poi_semantics():
    agent = MapAgent(api_key=AMAP_API_KEY)
    
    print("\n--- Testing POI Semantics ---")
    
    # Simulate a location in a busy area (Wangfujing, Beijing)
    # Using a known busy coordinate. This should find banks, convenience stores, etc.
    wangfujing_lonlat = "116.411132,39.912626" 
    
    print("\n[Test 1: Direct POI Search]")
    poi_name = agent.search_nearby_poi(wangfujing_lonlat)
    print(f"Discovered POI: {poi_name if poi_name else 'None found in whitelist'}")
    
    print("\n[Test 2: Cooldown Logic]")
    print("Searching same location immediately again...")
    poi_name_2 = agent.search_nearby_poi(wangfujing_lonlat)
    if poi_name_2 is None:
         print("Cooldown worked! (Returned None)")
    else:
         print(f"Cooldown FAILED. Returned: {poi_name_2}")
         
    # To test integration in guidance, we mock a route
    # Let's mock the internal variables to simulate being on a long straight path
    agent.current_route = True
    agent.nav_steps = [
         {"instruction": "向北步行500米右转", "polyline": "116.411132,39.912626;116.411132,39.917626", "action": "直行"}
    ]
    agent.current_step_index = 0
    
    # We clear the cooldown timestamp and history to test again
    agent.last_poi_time = 0 
    agent.announced_pois.clear()
    
    print("\n[Test 3: Integrated Guidance (Cruising mode > 15m)]")
    # We are at the start of the 500m segment, so dist_to_turn is ~500m
    # In map_agent, the dist_to_turn is calculated from current snapped location to the end of the polyline.
    # The end of our mock polyline is 116.411132,39.917626.
    
    # We need to simulate the exact condition. 
    # Currently get_navigation_guidance returns None if dist_to_turn >= 18 and no action is taken.
    # Ah wait! At line 286, it says `poi_name = self.search_nearby_poi` but only if it falls through.
    
    guidance = agent.get_navigation_guidance(wangfujing_lonlat, heading=0)
    print(f"Integrated Announcement: {guidance}")

if __name__ == "__main__":
    test_poi_semantics()
