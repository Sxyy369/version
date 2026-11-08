import pyttsx3
import time

print("Testing pyttsx3...")
engine = pyttsx3.init()
voices = engine.getProperty('voices')
for v in voices:
    if 'zh' in v.id.lower() or 'chinese' in v.id.lower():
        engine.setProperty('voice', v.id)
        print(f"Set voice to: {v.id}")
        break

engine.setProperty('rate', 200)
engine.say("测试一二三，能够听到我的声音吗？")
engine.runAndWait()
print("Speech finished.")
