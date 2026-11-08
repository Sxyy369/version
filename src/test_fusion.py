import sys
import os
import time

# Ensure the src directory is in the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.map_agent import MapAgent
from src.sensor_fusion import SensorFusion, MockIMU
from config import AMAP_API_KEY

def test_sensor_fusion_navigation():
    # 1. Initialize Modules
    agent = MapAgent(api_key=AMAP_API_KEY)
    fusion = SensorFusion(step_length=0.6) # 0.6m per step
    imu = MockIMU(fusion)
    
    # 2. Setup Route
    # We use a real segment for testing. 
    start_lonlat = "116.397428,39.90923"
    end_lonlat = "116.410886,39.914285"
    print("\n--- Route Planning ---")
    res = agent.get_walking_route(start_lonlat, end_lonlat)
    if not agent.current_route:
        print("Failed to get route.")
        return
        
    # 3. Setup Mock GPS Location 
    # Let's teleport the user to the end of the first polyline segment, just 10 meters before the turn.
    first_step = agent.nav_steps[0]
    points = first_step["polyline"].split(';')
    turn_point = points[-1]
    
    # For testing, we just use a point in the polyline directly to ensure we are on the line.
    # In reality, the turn point is the end of the first step.
    turn_lon, turn_lat = map(float, turn_point.split(','))
    
    # We will manually offset the latitude slightly south (so distance to turn is exactly ~10 meters)
    # 1 degree lat = 111132m.   10m = 10 / 111132 = 0.000089 degrees.
    start_lat = turn_lat - (10.0 / 111132.0)
    start_lon = turn_lon # Assume straight north
    
    # Simulate first GPS lock
    fusion.update_gps(lat=start_lat, lon=start_lon)
    fusion.update_heading(0) # Facing North
    
    print("\n--- Simulating GPS Loss + IMU Steps (PDR) ---")
    print(f"Goal Turn Point: {turn_lon:.6f}, {turn_lat:.6f}")
    print(f"Initial GPS Anchor: {start_lon:.6f}, {start_lat:.6f}")
    
    # Check Initial Guidance
    loc_str = fusion.get_fused_location_str()
    print(f"\n[Initial GPS Update]")
    print(f"Coords: {loc_str}")
    guidance = agent.get_navigation_guidance(loc_str, heading=fusion.heading)
    if guidance: print(f"播报: {guidance}")
    
    # Simulate walking 18 steps (18 * 0.6m = ~10.8m)
    # The user should hear the countdown: "还剩 X 米" -> then eventually turn.
    
    for i in range(1, 19):
        fusion.on_step_detected()
        loc_str = fusion.get_fused_location_str()
        
        # We simulate the app querying guidance every step
        print(f"\n[Step {i}] Coords: {loc_str}")
        guidance = agent.get_navigation_guidance(loc_str, heading=fusion.heading)
        if guidance: 
            print(f" -> 播报: {guidance}")
        
        # Stop testing if we reached the end of step 1 (successfully turned)
        if agent.current_step_index > 0:
            print("Successfully transitioned to next step!")
            break

if __name__ == "__main__":
    test_sensor_fusion_navigation()
