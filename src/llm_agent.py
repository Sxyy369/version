import cv2
import base64
import threading
import sys
import os
from openai import OpenAI
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import time

class LLMAgent:
    def __init__(self):
        self.api_key = config.LLM_API_KEY
        self.base_url = config.LLM_BASE_URL
        self.model = config.LLM_MODEL_NAME
        self.client = None
        self._is_thinking = False

        try:
            if self.api_key:
                self.client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url
                )
                print(f"[LLM] 初始化成功: {self.model}")
            else:
                print("[LLM] 未配置 API Key，功能已禁用。")
        except Exception as e:
            print(f"[LLM] 初始化失败: {e}")

    def is_thinking(self):
        return self._is_thinking

    def _encode_image(self, frame):
        """Convert CV2 frame to base64 string"""
        try:
            # Resize optimized for Qwen-VL (limit max dimension to 1024 or 512 for speed)
            # Qwen-VL supports high res, but for speed we can keep it reasonable. 640x480 is fine.
            # Convert to jpg
            _, buffer = cv2.imencode('.jpg', frame)
            # Encode to base64
            jpg_as_text = base64.b64encode(buffer).decode('utf-8')
            return jpg_as_text
        except Exception as e:
            print(f"[LLM] 图片编码错误: {e}")
            return None

    def analyze_scene_async(self, frame, callback_func, query=None):
        """
        异步分析场景
        frame: cv2 图像
        callback_func: 回调函数，接受 (text_result)
        query: Optional user question (str)
        """
        if self._is_thinking or not self.client:
            return

        self._is_thinking = True
        
        # Start a thread
        thread = threading.Thread(target=self._worker, args=(frame, callback_func, query))
        thread.daemon = True # Daemon thread exits when main program exits
        thread.start()

    def _worker(self, frame, callback_func, query=None):
        start_time = time.time()
        print("[LLM] 正在思考...")
        
        try:
            base64_image = self._encode_image(frame)
            if not base64_image:
                callback_func("图片处理失败")
                return
            
            # Construct Content
            user_content = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                }
            ]
            
            # If user has a specific query, append it OR use it as text input
            if query:
                # Add text query
                user_content.insert(0, {"type": "text", "text": query})
            
            # System prompt can remain or be slightly adjusted if query is present, 
            # but usually the system prompt (Assist Blind Person) is still valid context.

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": config.LLM_SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": user_content
                    }
                ],
                max_tokens=100  # Short answer
            )
            
            answer = response.choices[0].message.content.strip()
            print(f"[LLM] 思考完成 ({time.time() - start_time:.2f}s): {answer}")
            callback_func(answer)

        except Exception as e:
            print(f"[LLM] 请求失败: {e}")
            callback_func("网络请求出错")
        finally:
            self._is_thinking = False
