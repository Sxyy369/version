import asyncio
import threading
import pygame
import edge_tts
import time
import os
import queue
from config import ASSETS_DIR

# Ensure assets directory exists for temp audio files
os.makedirs(ASSETS_DIR, exist_ok=True)

class AudioAnnouncer:
    def __init__(self, voice="zh-CN-YunxiNeural", rate="+35%"):
        self.voice = voice
        self.rate = rate
        self.queue = queue.PriorityQueue()
        self.is_running = True
        self._is_processing = False 
        self.audio_cache = {} # Dict to store {text: filepath}
        
        # Initialize Pygame Mixer
        try:
            pygame.mixer.init()
        except Exception as e:
            print(f"Warning: Pygame mixer init failed: {e}")

        # Start worker thread
        self.thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.thread.start()

    def is_busy(self):
        """
        Check if TTS is currently speaking or has pending messages.
        """
        if not self.queue.empty():
            return True
        if self._is_processing:
            return True
        # Check actual playback status
        if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
            return True
        return False

    def clear_queue(self):
        """Clears all pending messages from the queue."""
        try:
            while not self.queue.empty():
                self.queue.get_nowait()
                self.queue.task_done()
        except queue.Empty:
            pass
            
    def interrupt(self):
        """Immediately stops current playback and clears queue."""
        self.clear_queue()
        if pygame.mixer.get_init():
            try:
                pygame.mixer.music.stop()
            except:
                pass
        self._is_processing = False

    def speak(self, text, priority=1):
        """
        Add text to the speech queue.
        """
        if not text:
            return
            
        # For Priority 0 (Warning), we interrupt everything
        if priority == 0:
            self.clear_queue()
            # If it's a warning, we might want to stop current playback immediately too?
            # For now, just clearing queue and letting current sentence finish usually feels more natural,
            # but for DANGER, we might want stop().
            # Let's stop playback for Priority 0 to be instant.
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
            
        self.queue.put((priority, text))

    def _worker_loop(self):
        """
        Background loop to process the queue.
        """
        while self.is_running:
            try:
                # Get item with blocking
                # Use a short timeout so we can check is_running
                priority, text = self.queue.get(timeout=0.1)
                
                self._is_processing = True
                # print(f"[TTS] Processing: {text} (P{priority})")
                
                # Check Cache
                audio_file = self.audio_cache.get(text)
                
                if audio_file and os.path.exists(audio_file):
                    # Cache Hit! Play immediately
                    # print(f"[TTS] Cache hit: {text}")
                    self._play_audio(audio_file)
                else:
                    # Cache Miss - Generate
                    print(f"[TTS] Generating (Net): {text}")
                    # Use a hash or clean text for filename
                    import hashlib
                    filename_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
                    cache_file = os.path.join(ASSETS_DIR, f"tts_{filename_hash}.mp3")
                    
                    try:
                        asyncio.run(self._generate_audio(text, cache_file))
                        # Update cache
                        self.audio_cache[text] = cache_file
                        # Play
                        self._play_audio(cache_file)
                    except Exception as e:
                        print(f"[TTS] Gen/Play Error: {e}")
                
                self.queue.task_done()
                self._is_processing = False
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[TTS] Loop Error: {e}")
                self._is_processing = False

    async def _generate_audio(self, text, output_file):
        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate)
        await communicate.save(output_file)

    def _play_audio(self, file_path):
        if not pygame.mixer.get_init():
            return

        try:
            pygame.mixer.music.load(file_path)
            pygame.mixer.music.play()
            
            # Wait for playback to finish
            while pygame.mixer.music.get_busy() and self.is_running:
                # Check for interruption signal from queue (if high priority comes in?)
                # For now simple block is safer for thread sync
                pygame.time.Clock().tick(20)
                
            # Unload to release file
            # pygame.mixer.music.unload() 
        except Exception as e:
            print(f"[TTS] Playback error: {e}")

    def stop(self):
        self.is_running = False
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
            pygame.mixer.quit()
