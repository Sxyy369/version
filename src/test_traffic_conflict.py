import sys
import os
import cv2
import numpy as np

# Ensure the src directory is in the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.navigator import BlindPathNavigator

def test_intersection_logic():
    print("\n--- Testing Intersection Vision Logic ---")
    
    # Initialize Navigator
    # Note: For simple testing, we just use the logic, model might fail to load if files missing, 
    # but the logic function _check_obstacles is independent of model inference if we provide mock detections.
    nav = BlindPathNavigator()
    
    # Mock settings
    w, h = 640, 480
    
    # Test Case 1: Normal Walking + Red Light (Far away)
    print("\n[Case 1: Normal Walking - Red Light]")
    nav.set_intersection_mode(False)
    mock_detections_1 = [{'class_id': 9, 'tl_color': 'Red', 'box': [100, 100, 150, 150]}]
    cmd, debug = nav._check_obstacles(mock_detections_1, w, h)
    print(f"Result: {cmd} | {debug}")
    
    # Test Case 2: Normal Walking + Green Light 
    print("\n[Case 2: Normal Walking - Green Light]")
    nav.set_intersection_mode(False)
    mock_detections_2 = [{'class_id': 9, 'tl_color': 'Green', 'box': [100, 100, 150, 150]}]
    cmd, debug = nav._check_obstacles(mock_detections_2, w, h)
    print(f"Result (Should be None): {cmd} | {debug}")
    
    # Test Case 3: At Intersection + Red Light
    print("\n[Case 3: At Intersection - Red Light]")
    nav.set_intersection_mode(True)
    mock_detections_3 = [{'class_id': 9, 'tl_color': 'Red', 'box': [100, 100, 150, 150]}]
    cmd, debug = nav._check_obstacles(mock_detections_3, w, h)
    print(f"Result (Should trigger ALARM): {cmd} | {debug}")
    
    # Test Case 4: At Intersection + Green Light + Clear Path
    print("\n[Case 4: At Intersection - Green Light - Clear Path]")
    nav.set_intersection_mode(True)
    mock_detections_4 = [{'class_id': 9, 'tl_color': 'Green', 'box': [100, 100, 150, 150]}]
    cmd, debug = nav._check_obstacles(mock_detections_4, w, h)
    print(f"Result (Should trigger GO): {cmd} | {debug}")
    
    # Test Case 5: At Intersection + Green Light + Car blocking crosswalk
    print("\n[Case 5: At Intersection - Green Light - Car Blocking]")
    nav.set_intersection_mode(True)
    # Car (class 2) is at y=300 to y=400 (bottom half of screen -> close)
    mock_detections_5 = [
        {'class_id': 9, 'tl_color': 'Green', 'box': [100, 100, 150, 150]},
        {'class_id': 2, 'box': [200, 300, 400, 400]} 
    ]
    cmd, debug = nav._check_obstacles(mock_detections_5, w, h)
    print(f"Result (Should fall through to Obstacle logic/None for GO): {cmd} | {debug}")

if __name__ == "__main__":
    test_intersection_logic()
