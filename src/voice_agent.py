import speech_recognition as sr
import threading
import time

class VoiceAgent:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.microphone = None
        self.is_listening = False
        
        try:
            # Index 3 is "阵列麦克风 (AMD Audio Device)" based on user logs
            # Index 1 was "ToDesk Virtual Audio" which caused silence
            # We try to use Index 3 explicitly.
            self.microphone = sr.Microphone(device_index=3)
            print("[VOICE] Microphone initialized (Device Index 3).")
        except Exception as e:
            print(f"[VOICE ERROR] Failed to init specific mic, trying default: {e}")
            try:
                self.microphone = sr.Microphone()
            except Exception as e2:
                 print(f"[VOICE FATAL] No mic: {e2}")
        
        # VAD Tuning for Slower Speech / Thinking Pauses
        self.recognizer.pause_threshold = 1.5 # Wait 1.5s silence before stopping
        self.recognizer.energy_threshold = 300 # Adjust sensitivity if needed

    def listen_once(self):
        """
        Listen for a single phrase and return text.
        Blocking call (run in thread recommended).
        """
        if not self.microphone:
            return None

        with self.microphone as source:
            print("[VOICE] Adjusting for ambient noise...")
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
            print("[VOICE] Listening...")
            try:
                # Timeout: wait 10s for speech to start
                # Phrase_time_limit: max 15s of speech
                audio = self.recognizer.listen(source, timeout=10, phrase_time_limit=15)
                print("[VOICE] Processing audio...")
                
                # Save audio to temporary file
                temp_filename = "temp_speech.wav"
                with open(temp_filename, "wb") as f:
                     f.write(audio.get_wav_data())
                
                print("[VOICE] Sending to SiliconFlow Cloud...")
                
                # Use SiliconFlow API (OpenAI Compatible)
                import config
                from openai import OpenAI
                import os
                
                if not config.LLM_API_KEY:
                    print("[VOICE] No API Key found.")
                    return None
                    
                client = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)
                
                try:
                    with open(temp_filename, "rb") as audio_file:
                        # Use correct model ID from API list
                        transcription = client.audio.transcriptions.create(
                            model="FunAudioLLM/SenseVoiceSmall", 
                            file=audio_file
                        )
                    text = transcription.text
                    print(f"[VOICE] Recognized: {text}")
                    return text
                    
                except Exception as e:
                    print(f"[VOICE] SiliconFlow API Error: {e}")
                    # Fallback to Sphinx if offline? (Optional, usually bad for CN)
                    return None
                finally:
                    # Cleanup
                    if os.path.exists(temp_filename):
                        try:
                             os.remove(temp_filename)
                        except: pass

            except sr.WaitTimeoutError:
                print("[VOICE] Timeout: No speech detected.")
                return None
            except Exception as e:
                print(f"[VOICE] Error: {e}")
                return None

    def classify_intent(self, text):
        """
        Heuristic intent classification.
        Returns: (intent_type, content)
        Types: 'NAV', 'CHAT', 'NONE'
        """
        if not text: return "NONE", None
        
        # 0. Detect Mode
        mode = "walking" # default
        if any(k in text for k in ["驾车", "开车", "打车", "出租车"]):
            mode = "driving"
        elif any(k in text for k in ["公交", "地铁", "巴士", "坐车"]):
            mode = "transit"
        
        # 1. Navigation Control Commands
        if "下一步" in text or "继续" in text:
            return "NAV_CONTROL", "NEXT"
        if "上一步" in text:
            return "NAV_CONTROL", "PREV"
        if "重复" in text or "再说一遍" in text:
            return "NAV_CONTROL", "REPEAT"
        if "停止导航" in text or "退出导航" in text or "结束导航" in text:
            return "NAV_CONTROL", "STOP"

        # 1.5 Query Location
        if any(k in text for k in ["我在哪", "我的位置", "当前位置", "定位"]):
            # If it's a simple query, return QUERY intent
            # But "从当前位置导航..." is NAV_FLEX
            if "导航" not in text and "去" not in text:
                return "QUERY_LOCATION", None

        # 2. "From A to B" Pattern (Flexible Routing)
        # Regex is better but simple string parsing works for fixes
        if "从" in text and ("到" in text or "去" in text):
            try:
                # E.g. "从天安门到故宫"
                start_part = text.split("从")[1]
                if "到" in start_part:
                    start_loc, end_loc = start_part.split("到", 1)
                else:
                    start_loc, end_loc = start_part.split("去", 1)
                
                # Cleanup common words that break search
                # E.g. "从A导航到B", "从A去往B的路线"
                for junk in ["导航", "前往", "的路线", "路线", "去往", "查看", "一下", "坐车", "打车", "驾车", "公交"]:
                    start_loc = start_loc.replace(junk, "")
                    end_loc = end_loc.replace(junk, "")

                start_loc = start_loc.strip().strip("。.,，！! ")
                end_loc = end_loc.strip().strip("。.,，！! ")
                
                # Normalize "Current Location"
                if any(k in start_loc for k in ["当前位置", "我的位置", "这里", "在这"]):
                    start_loc = "CURRENT_LOC"

                if start_loc and end_loc:
                    print(f"[VOICE DEBUG] Flexible Route: {start_loc} -> {end_loc} Mode: {mode}")
                    return "NAV_FLEX", {"start": start_loc, "end": end_loc, "mode": mode}
            except:
                pass

        # 3. Standard Navigation (Current Location -> Dest)
        nav_keywords = ["导航", "去", "带我到", "路线", "怎么走"]
        
        if any(k in text for k in nav_keywords):
            # Extract destination (simple split)
            best_dest = None
            for k in nav_keywords:
                if k in text:
                    parts = text.split(k)
                    if len(parts) > 1:
                        candidate = parts[1].strip().strip("。.,，！!")
                # Remove common politeness words from destination
                        for junk in ["一下", "嘛", "呗", "坐车", "打车", "驾车", "公交", "附近的", "离我最近的", "最近的", "附近", "最近"]:
                            candidate = candidate.replace(junk, "")
                        
                        if candidate:
                            best_dest = candidate
                            break
            
            # If after splitting we found a destination, return match
            if best_dest:
                # Return dict now for consistency and mode support
                return "NAV", {"dest": best_dest, "mode": mode}
            
            # If keywords present but no destination found (e.g. "帮我导航", "我要去哪里")
            # Return special intent to prompt user
            return "NAV_ASK_DEST", None
            
        return "CHAT", text

if __name__ == "__main__":
    # Test
    agent = VoiceAgent()
    if agent.microphone:
        txt = agent.listen_once()
        if txt:
            intent, content = agent.classify_intent(txt)
            print(f"Intent: {intent}, Content: {content}")
