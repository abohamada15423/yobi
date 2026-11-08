"""Oracle 'APM' for tests: knows the simulated echo of the current block and
removes (1-residual) of it. Verifies Yobi's plumbing, not WebRTC's maths."""
import numpy as np
RESIDUAL = {"v": 0.05}
class AudioFrame:
    def __init__(self, data, sample_rate, num_channels, samples_per_channel):
        self._data = bytearray(data); self.sample_rate = sample_rate
    @property
    def data(self): return memoryview(self._data).cast("h")
class AudioProcessingModule:
    INSTANCES = []
    def __init__(self, echo_cancellation=False, noise_suppression=False, high_pass_filter=False, auto_gain_control=False):
        self.aec = echo_cancellation; self.rev_frames = 0; self.rev_energy = 0.0; self.cap_frames = 0; self.delay_ms = None
        AudioProcessingModule.INSTANCES.append(self)
    def process_reverse_stream(self, f):
        self.rev_frames += 1
        r = np.frombuffer(bytes(f._data), np.int16).astype(np.float32); self.rev_energy += float(np.mean(r*r))
    def set_stream_delay_ms(self, d): self.delay_ms = d
    def process_stream(self, f):
        import sounddevice as sd
        self.cap_frames += 1
        x = np.frombuffer(bytes(f._data), np.int16).astype(np.float32)
        if self.aec:
            e = sd.MIC.get("last_echo")
            if e is not None and len(e) == len(x):
                x = x - (1 - RESIDUAL["v"]) * e
        f._data[:] = np.clip(x, -32768, 32767).astype(np.int16).tobytes()
