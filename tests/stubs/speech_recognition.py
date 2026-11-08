class WaitTimeoutError(Exception): pass
class AudioData:
    def __init__(self, frame_data, sample_rate, sample_width):
        self.frame_data = frame_data; self.sample_rate = sample_rate; self.sample_width = sample_width
    def get_wav_data(self):
        import io, wave
        b = io.BytesIO()
        with wave.open(b, "wb") as w:
            w.setnchannels(1); w.setsampwidth(self.sample_width); w.setframerate(self.sample_rate); w.writeframes(self.frame_data)
        return b.getvalue()
