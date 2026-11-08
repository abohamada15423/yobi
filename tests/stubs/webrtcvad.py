import numpy as np
class Vad:
    def __init__(self, mode=2): self.mode = mode
    def is_speech(self, frame, sr):
        a = np.frombuffer(frame, np.int16).astype(np.float32)
        return float(np.sqrt(np.mean(a*a))) > (900 if self.mode >= 3 else 600)
