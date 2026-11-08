import sys
import os

# Ensure the src directory is in the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.map_agent import MapAgent
from config import AMAP_API_KEY

def test_clock_directions():
    agent = MapAgent(api_key=AMAP_API_KEY)
    
    # Example locations (e.g. from Tiananmen to Wangfujing)
    start_lonlat = "116.397428,39.90923"
    end_lonlat = "116.410886,39.914285"
    
    print("\n--- 1. Testing Route Planning ---")
    res = agent.get_walking_route(start_lonlat, end_lonlat)
    print(res)
    
    if not agent.current_route:
        print("Failed to get route. Make sure AMAP_API_KEY is valid.")
        return
        
    print("\n--- 2. Testing Guidance with Headings ---")
    
    # We will simulate being exactly at the start point, but facing different directions
    # To trigger the "Next" step instruction, we need to be close to the first turn.
    # Let's forcefully set step index to 0 and pretend we are exactly at the end of the first polyline
    
    first_step = agent.nav_steps[0]
    points = first_step["polyline"].split(';')
    end_of_first_step = points[-1] # This is where the turn happens
    
    # Simulating arriving at the turn point
    curr_location = end_of_first_step
    
    headings_to_test = [
        (0, "面朝正北"),
        (90, "面朝正东"),
        (180, "面朝正南"),
        (270, "面朝正西")
    ]
    
    for heading, desc in headings_to_test:
        # Reset index to test the exact same turn multiple times
        agent.current_step_index = 0 
        
        guidance = agent.get_navigation_guidance(curr_location, heading=heading)
        print(f"[{desc} (Heading: {heading}°)] -> 播报: {guidance}")

    print("\n--- 3. Testing Anticipatory Snapping (Moving to next segment) ---")
    if len(agent.nav_steps) > 1:
        second_step_points = agent.nav_steps[1]["polyline"].split(';')
        if len(second_step_points) > 2:
            # Pick a point slightly into the second segment
            slightly_into_second = second_step_points[1]
            agent.current_step_index = 0 # Assume we haven't updated yet
            
            print(f"Moving to point on Step 2: {slightly_into_second}")
            # Facing North
            guidance = agent.get_navigation_guidance(slightly_into_second, heading=0)
            print(f"[Moved into next segment] -> 播报: {guidance}")

if __name__ == "__main__":
    test_clock_directions()
