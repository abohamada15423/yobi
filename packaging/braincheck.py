# -*- coding: utf-8 -*-
"""Run with the build's Python inside an installed copy that has a key in .env:
Gemini hears a recorded command and answers a question — the cloud path a friend uses.

    runtime/python.exe -s -E -X utf8 braincheck.py <app dir> <a .wav of a command>"""
import os
import sys
import time

app, wav = os.path.abspath(sys.argv[1]), sys.argv[2]
sys.path.insert(0, app)
os.chdir(app)
import speech_recognition as sr  # noqa: E402

import agent  # noqa: E402  (module setup only: keys, model pick; the assistant loop runs under __main__)

ok = True
with open(wav, "rb") as f:
    import io
    import wave
    with wave.open(io.BytesIO(f.read())) as w:
        audio = sr.AudioData(w.readframes(w.getnframes()), w.getframerate(), w.getsampwidth())
t = time.time()
try:
    text = agent.transcribe_groq(audio, prompt_text="يا يوبي، افتح، شغل")
    print(f"cloud STT: {text!r} in {time.time() - t:.1f}s")
    ok &= bool(text)
except Exception as e:
    ok = False
    print("cloud STT FAILED:", type(e).__name__, e)
t = time.time()
try:
    r = agent.groq_client.chat.completions.create(
        model=agent._pick_working_model(),
        messages=[{"role": "user", "content": "رد بكلمة واحدة بالمصري: إزيك؟"}])
    answer = r.choices[0].message.content
    print(f"brain: {answer!r} in {time.time() - t:.1f}s")
    ok &= bool(answer)
except Exception as e:
    ok = False
    print("brain FAILED:", type(e).__name__, e)
print("BRAINCHECK", "OK" if ok else "FAILED")
sys.stdout.flush()
os._exit(0)
