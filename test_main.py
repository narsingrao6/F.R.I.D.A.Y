import queue
import time
from main import _friday_logic

class MockAPI:
    def __init__(self):
        self.ui_state = {"micOn": False}
    def set_phase(self, phase):
        print(f"Phase: {phase}")
    def push_message(self, sender, text):
        print(f"Message ({sender}): {text}")

q = queue.Queue()
api = MockAPI()

import threading
t = threading.Thread(target=_friday_logic, args=(api, q))
t.daemon = True
t.start()

time.sleep(2)
print("Injecting command: open chrome")
q.put(("open chrome", "en", None, False))

time.sleep(2)
print("Injecting command: close it")
q.put(("close it", "en", None, False))

time.sleep(2)
print("Injecting command: brightness penchu")
q.put(("brightness penchu", "te", None, False))

time.sleep(2)
print("Injecting command: friday is stuck at processing")
q.put(("friday is stuck at processing", "en", None, False))

time.sleep(4)
print("Done")
