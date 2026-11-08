import numpy as np
class Model:
    """Fake: scores 0.9 while the chunk contains a 'wake' tone at ~700 Hz."""
    def __init__(self, wakeword_models=None, inference_framework="onnx", vad_threshold=0.0):
        self.name = "ya_yobi"
    def predict(self, chunk):
        x = np.asarray(chunk, np.float32)
        if not x.any(): return {self.name: 0.0}
        sp = np.abs(np.fft.rfft(x)); f = np.fft.rfftfreq(len(x), 1/16000)
        band = sp[(f > 650) & (f < 750)].sum() / (sp.sum() + 1e-9)
        return {self.name: 0.9 if band > 0.3 else 0.02}
    def reset(self): pass
