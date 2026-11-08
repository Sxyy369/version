from rapidocr_onnxruntime import RapidOCR
import time

class TextRecognizer:
    def __init__(self):
        print("[OCR] Initializing RapidOCR...")
        # RapidOCR initializes very quickly compared to Paddle
        self.ocr = RapidOCR()
        print("[OCR] Initialization Complete.")

    def recognize(self, frame):
        """
        Recognize text in the given frame using RapidOCR.
        
        Args:
            frame (numpy.ndarray): Input image.
            
        Returns:
            list: List of strings found in the image.
        """
        if frame is None:
            return []

        start_time = time.time()
        
        # RapidOCR accepts numpy array directly
        # Returns: list of [dt_boxes, rec_res, score]
        result, elapse = self.ocr(frame)
        
        texts = []
        if result:
            for line in result:
                # line structure: [coords, text, confidence]
                text = line[1]
                confidence = float(line[2])
                
                if confidence > 0.5: # Threshold
                    texts.append(text)
        
        if texts:
            print(f"[OCR] Processed in {time.time() - start_time:.2f}s. Found: {texts}")
        return texts
