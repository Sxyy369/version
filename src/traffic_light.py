import cv2
import numpy as np

def analyze_traffic_light(image_crop):
    """
    Analyze the traffic light crop to determine the state (Red, Green, Yellow).
    
    Args:
        image_crop (numpy.ndarray): The cropped image of the traffic light.
        
    Returns:
        str: "Red", "Green", "Yellow", or "Unknown"
    """
    if image_crop is None or image_crop.size == 0:
        return "Unknown"

    # Convert to HSV color space
    hsv = cv2.cvtColor(image_crop, cv2.COLOR_BGR2HSV)
    
    # Define color ranges in HSV
    # Note: Hue range is 0-179 in OpenCV
    
    # Red: covers two ranges (0-10 and 160-180)
    lower_red1 = np.array([0, 70, 50])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([160, 70, 50])
    upper_red2 = np.array([179, 255, 255])
    
    # Green
    lower_green = np.array([35, 70, 50])
    upper_green = np.array([85, 255, 255])
    
    # Yellow
    lower_yellow = np.array([20, 70, 50])
    upper_yellow = np.array([34, 255, 255])
    
    # Create masks
    mask_red1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask_red2 = cv2.inRange(hsv, lower_red2, upper_red2)
    mask_red = cv2.bitwise_or(mask_red1, mask_red2)
    
    mask_green = cv2.inRange(hsv, lower_green, upper_green)
    mask_yellow = cv2.inRange(hsv, lower_yellow, upper_yellow)
    
    # Count non-zero pixels
    red_count = cv2.countNonZero(mask_red)
    green_count = cv2.countNonZero(mask_green)
    yellow_count = cv2.countNonZero(mask_yellow)
    
    # Simple voting
    max_count = max(red_count, green_count, yellow_count)
    
    # Threshold for noise (optional, requires tuning)
    if max_count < 10: 
        return "Unknown"
    
    if max_count == red_count:
        return "Red"
    elif max_count == green_count:
        return "Green"
    elif max_count == yellow_count:
        return "Yellow"
    
    return "Unknown"
