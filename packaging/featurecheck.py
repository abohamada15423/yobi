# -*- coding: utf-8 -*-
"""Run with the build's Python: the online voice (Edge TTS → mp3) and the offline speech model
(faster-whisper small on the CPU, no GPU libraries) really work inside the build.

    runtime/python.exe -s -E featurecheck.py <app dir> <a .wav of someone talking>"""
import asyncio
import io
import os
import sys
import time

app, wav = os.path.abspath(sys.argv[1]), sys.argv[2]
sys.path.insert(0, app)
ok = True

t = time.time()
try:
    import edge_tts
    out = os.path.join(os.environ.get("TEMP", "."), "yobi_tts_check.mp3")
    asyncio.run(edge_tts.Communicate("أهلاً، أنا يوبي", "ar-EG-SalmaNeural").save(out))
    print(f"TTS ok: {os.path.getsize(out)} bytes in {time.time() - t:.1f}s")
    os.remove(out)
except Exception as e:
    ok = False
    print("TTS FAILED:", type(e).__name__, e)

t = time.time()
try:
    from faster_whisper import WhisperModel
    m = WhisperModel("small", device="cpu", compute_type="int8")
    load = time.time() - t
    t = time.time()
    with open(wav, "rb") as f:
        segs, _ = m.transcribe(io.BytesIO(f.read()), language="ar", beam_size=1, vad_filter=True)
        text = "".join(s.text for s in segs).strip()
    print(f"local STT ok: load {load:.1f}s, heard in {time.time() - t:.1f}s: {text!r}")
except Exception as e:
    ok = False
    print("local STT FAILED:", type(e).__name__, e)
print("FEATURECHECK", "OK" if ok else "FAILED")
