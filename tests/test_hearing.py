# -*- coding: utf-8 -*-
"""Hearing v4 tests — run: python -m unittest tests/test_hearing.py
Uses stubs (tests/stubs) for sounddevice / webrtcvad / speech_recognition /
livekit / openwakeword so it runs on any machine without audio hardware."""
import io, json, os, sys, tempfile, threading, time, unittest, wave
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "stubs"))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import numpy as np
import sounddevice as fake_sd
import speech_recognition as sr

import latency, vocab, audio_io, wake_word, audio_input, stt_engine
from arabic_text import normalize_ar, cer, wer


def tone(freq, n, amp=8000, sr_=16000, t0=0):
    t = (np.arange(n) + t0) / sr_
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def noise(n, amp=4000, seed=0):
    return (np.random.default_rng(seed).standard_normal(n) * amp).astype(np.float32)


class Scenario:
    """Mic timeline: list of (start_s, end_s, kind) relative to t0."""
    def __init__(self, segments):
        self.t0 = time.time(); self.seg = segments; self.k = 0
    def __call__(self, n, now):
        el = now - self.t0
        self.k += 1
        for a, b, kind in self.seg:
            if a <= el < b:
                if kind == "speech":
                    return noise(n, 5000, self.k) * (0.6 + 0.4 * np.sin(el * 25))
                if kind == "wake":
                    return tone(700, n, 9000, t0=self.k * n)
                if kind == "loud":
                    return noise(n, 7000, self.k)
        return noise(n, 60, self.k)


class TestDSP(unittest.TestCase):
    def test_decimator_streaming_equals_oneshot(self):
        x = tone(1000, 48000 * 1, 10000, sr_=48000).astype(np.int16)
        d1 = audio_io.Decimator(3); one = d1.process(x)
        d2 = audio_io.Decimator(3); parts = []
        i = 0
        for bs in [480, 479, 481, 1000, 7, 333] * 30:
            if i >= len(x): break
            parts.append(d2.process(x[i:i + bs])); i += bs
        two = np.concatenate(parts)[:len(one)]
        self.assertEqual(len(one), 16000)
        self.assertLess(np.max(np.abs(one[:len(two)].astype(int) - two.astype(int))), 2)
        # 1 kHz survives with ~same amplitude
        self.assertAlmostEqual(np.std(one[200:]) * np.sqrt(2), 10000, delta=400)

    def test_decimator_rejects_alias(self):
        x = tone(12000, 48000, 10000, sr_=48000).astype(np.int16)   # above 8 kHz Nyquist
        y = audio_io.Decimator(3).process(x)
        self.assertLess(np.std(y[200:]), 400)

    def test_resample(self):
        y = audio_io.resample(np.zeros(24000, np.int16), 24000, 48000)
        self.assertEqual(len(y), 48000)
        y = audio_io.resample(np.zeros(22050, np.int16), 22050, 48000)
        self.assertAlmostEqual(len(y), 48000, delta=2)


class TestLatency(unittest.TestCase):
    def test_turn(self):
        logs = []
        with tempfile.TemporaryDirectory() as d:
            csvp = os.path.join(d, "lat.csv")
            tr = latency.LatencyTracker(csv_path=csvp, log=logs.append, summary_every=2)
            for k in range(2):
                tr.start_turn(100.0)
                tr.mark("stt_start", 100.0); tr.mark("stt_done", 100.4, info="groq-turbo")
                tr.mark("llm_start", 100.45); tr.mark("llm_first", 101.0)
                tr.mark("tts_request", 101.0); tr.mark("tts_request", 105.0)  # once
                tr.mark("first_audio", 101.3)
                time.sleep(0.05)
            self.assertIn("STT 400ms (groq-turbo)", logs[0])
            self.assertIn("LLM أول جملة 550ms", logs[0])
            self.assertIn("TTS أول صوت 300ms", logs[0])
            self.assertIn("الإجمالي 1.30s", logs[0])
            self.assertTrue(any("p50" in l for l in logs))
            rows = open(csvp, encoding="utf-8").read().splitlines()
            self.assertEqual(len(rows), 3)

    def test_marks_without_turn_ignored(self):
        tr = latency.LatencyTracker(log=lambda m: None)
        tr.mark("stt_done"); self.assertIsNone(tr.current())


class TestVocab(unittest.TestCase):
    def test_prompt_ranking_budget_fixes(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "vocab.json")
            json.dump({"friends": ["كريم"], "fixes": {"فالورنت": "Valorant"}}, open(p, "w", encoding="utf-8"))
            targets = ["discord", "steam://rungameid/123", "C:\\x\\a.exe", "spotify", "notepad.exe", "rocket_league"]
            v = vocab.PersonalVocab(path=p, max_chars=60, targets_source=lambda: targets)
            v.bump("spotify"); v.bump("spotify")
            pr = v.prompt(base="أوامر:")
            self.assertTrue(pr.startswith("أوامر:، كريم، Valorant، spotify"))
            self.assertLessEqual(len(pr), 60)
            self.assertNotIn("steam://", pr); self.assertNotIn("\\", pr)
            self.assertIn("rocket league", v.terms())
            self.assertEqual(v.apply_fixes("افتح فالورنت"), "افتح Valorant")
            self.assertIn("spotify", json.load(open(p, encoding="utf-8"))["usage"])


class TestArabicMetrics(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_ar("أَفْتَحْ إيه؟ الصورة"), "افتح ايه الصوره")
        self.assertEqual(cer("افتح سبوتيفاي", "إفتح سبوتيفاى"), 0.0)
        self.assertAlmostEqual(wer("افتح سبوتيفاي دلوقتي", "افتح سبوتي دلوقتي"), 1 / 3)


class FakeGroq:
    def __init__(self, fail=False, text="افتح فالورنت"):
        self.fail = fail; self.calls = []; outer = self
        class T:
            def create(self_, **kw):
                outer.calls.append(kw)
                if outer.fail: raise ConnectionError("offline")
                class R: pass
                r = R(); r.text = text; return r
        class A: transcriptions = T()
        self.audio = A()


class FakeLocal:
    def __init__(self): self.kw = None
    def transcribe(self, f, **kw):
        self.kw = kw
        class S: text = " شغل سبوتيفاي"
        return [S()], None


class TestSTT(unittest.TestCase):
    def audio(self):
        return sr.AudioData(np.zeros(1600, np.int16).tobytes(), 16000, 2)

    def test_groq_turbo_first_and_fixes(self):
        g = FakeGroq()
        with tempfile.TemporaryDirectory() as d:
            v = vocab.PersonalVocab(path=os.path.join(d, "v.json"))
            v.fixes = {"فالورنت": "Valorant"}
            e = stt_engine.STTEngine(g, vocab=v, log=lambda m: None)
            self.assertEqual(e.transcribe(self.audio(), prompt="p"), "افتح valorant")
            self.assertEqual(g.calls[0]["model"], "whisper-large-v3-turbo")
            self.assertEqual(e.last_engine, "groq-turbo")

    def test_offline_fallback_local_and_breaker(self):
        g = FakeGroq(fail=True); loc = FakeLocal()
        e = stt_engine.STTEngine(g, log=lambda m: None)
        e._local = loc
        self.assertEqual(e.transcribe(self.audio(), prompt="hint"), "شغل سبوتيفاي")
        self.assertEqual(e.last_engine, "local")
        self.assertEqual(loc.kw["initial_prompt"], "hint")
        e.transcribe(self.audio())
        n = len(g.calls)
        e.transcribe(self.audio())          # circuit open → groq skipped
        self.assertEqual(len(g.calls), n)

    def test_latency_marks(self):
        logs = []
        latency.tracker.configure(log=logs.append, csv_path="")
        latency.tracker._csv = None
        latency.start_turn()
        e = stt_engine.STTEngine(FakeGroq(), log=lambda m: None)
        e.transcribe(self.audio())
        cur = latency.tracker.current()
        self.assertIn("stt_done", cur); self.assertEqual(cur["stt_done_info"], "groq-turbo")

    def test_romanized_arabic_is_reheard(self):
        g = FakeGroq(); outer = g
        texts = {"whisper-large-v3-turbo": "uptah, lúlí", "whisper-large-v3": "افتح لول"}
        class T:
            def create(self_, **kw):
                outer.calls.append(kw)
                class R: pass
                r = R(); r.text = texts[kw["model"]]; return r
        g.audio.transcriptions = T()
        e = stt_engine.STTEngine(g, log=lambda m: None)
        e._local = FakeLocal()
        self.assertEqual(e.transcribe(self.audio()), "افتح لول")
        self.assertEqual([c["model"] for c in g.calls],
                         ["whisper-large-v3-turbo", "whisper-large-v3"])
        self.assertEqual(e.last_engine, "groq-v3")

    def test_real_english_command_not_reheard(self):
        g = FakeGroq(text="open chrome")
        e = stt_engine.STTEngine(g, log=lambda m: None)
        self.assertEqual(e.transcribe(self.audio()), "open chrome")
        self.assertEqual(len(g.calls), 1)
        self.assertTrue(e.looks_romanized("ufta hlúl"))
        self.assertTrue(e.looks_romanized("iftah el yutyub"))
        self.assertFalse(e.looks_romanized("افتح valorant"))

    def test_hallucination_filtered(self):
        e = stt_engine.STTEngine(FakeGroq(text="اشتركوا في القناة"), is_hallucination=lambda t: "اشتركوا" in t, log=lambda m: None)
        self.assertEqual(e.transcribe(self.audio()), "")


class EngineCase(unittest.TestCase):
    def setUp(self):
        fake_sd.MIC.update(source=None, echo_gain=0.0, echo_delay=0.05)
        fake_sd.SPEAKER.clear()
        import livekit.rtc as rtc
        rtc.RESIDUAL["v"] = 0.05
        self.eng = audio_io.AudioEngine(aec=True, log=lambda m: None)
        audio_io.set_audio_engine(self.eng)

    def tearDown(self):
        self.eng.close(); audio_io.set_audio_engine(None)
        time.sleep(0.05)


class TestAudioEngine(EngineCase):
    def test_play_blocks_then_drains_and_feeds_reference(self):
        frames = []
        self.eng.subscribe(lambda f, t: frames.append(len(f)))
        started = threading.Event()
        t0 = time.time()
        ok = self.eng.play(tone(440, 24000 // 2, 8000, sr_=24000).astype(np.int16), 24000, on_start=started.set)
        self.assertTrue(ok); self.assertTrue(started.is_set())
        self.assertGreater(time.time() - t0, 0.4)
        apm = self.eng._apm
        self.assertTrue(self.eng.aec_active)
        self.assertGreater(apm.rev_frames, 40); self.assertGreater(apm.rev_energy, 1e6)
        self.assertIsNotNone(apm.delay_ms)
        self.assertTrue(frames and set(frames) == {160})

    def test_stop_playback(self):
        ev = threading.Event()
        threading.Timer(0.2, ev.set).start()
        t0 = time.time()
        ok = self.eng.play(np.zeros(48000 * 3, np.int16) + 1000, 48000, stop_event=ev)
        self.assertFalse(ok); self.assertLess(time.time() - t0, 0.6)
        self.assertFalse(self.eng.is_playing() and self.eng._speech.size)

    def test_fx_mix(self):
        self.eng.play_fx(audio_io.tone([880], [100]), 48000)
        time.sleep(0.25)
        heard = np.concatenate([c for _, c in list(fake_sd.SPEAKER)[-40:]])
        self.assertGreater(np.abs(heard).max(), 3000)

    def test_echo_removed_for_subscribers(self):
        fake_sd.MIC["echo_gain"] = 0.8
        raw, clean = [], []
        self.eng.subscribe(lambda f, t: raw.append(f.copy()), raw=True)
        self.eng.subscribe(lambda f, t: clean.append(f.copy()))
        self.eng.play(noise(48000, 6000).astype(np.int16), 48000)
        r = np.concatenate(raw[20:]).astype(np.float32); c = np.concatenate(clean[20:]).astype(np.float32)
        erle = 10 * np.log10((np.mean(r * r) + 1) / (np.mean(c * c) + 1))
        self.assertGreater(erle, 15)
        self.assertIsNotNone(self.eng.erle_db)


class TestWakeDetector(unittest.TestCase):
    def test_detect_patience_cooldown_boost(self):
        hits = []
        det = wake_word.WakeWordDetector("fake_model", threshold=0.5, patience=2, cooldown=1.0,
                                         on_detect=lambda s, t: hits.append(t), log=lambda m: None)
        t = 100.0
        for i in range(6):                    # 6 × 80 ms of 'wake' tone
            det.feed(tone(700, 1280, 9000, t0=i * 1280).astype(np.int16), t); t += 0.08
        time.sleep(0.3)
        self.assertTrue(det.event.is_set()); self.assertEqual(len(hits), 1)
        det.reset()
        det.boost = 0.5                       # threshold 1.0 → never
        for i in range(6):
            det.feed(tone(700, 1280, 9000).astype(np.int16), t + 5); t += 0.08
        time.sleep(0.3)
        self.assertFalse(det.event.is_set())

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            wake_word.WakeWordDetector("models/nope.onnx", log=lambda m: None)


class TestRecognizer(EngineCase):
    def make(self, speaking=lambda: False, stop=lambda: None, wake=None, barge="auto"):
        return audio_input.VADRecognizer(hotkey=None, engine=self.eng, wake=wake,
                                         is_speaking=speaking, stop_speaking=stop,
                                         barge_in=barge, log=lambda m: None)

    def test_listen_captures_utterance_and_starts_latency_turn(self):
        latency.tracker.configure(log=lambda m: None); latency.tracker._csv = None
        rec = self.make()
        fake_sd.MIC["source"] = Scenario([(0.3, 1.2, "speech")])
        audio = rec.listen(timeout=3, phrase_time_limit=5)
        dur = len(audio.frame_data) / 2 / 16000
        self.assertGreater(dur, 0.8); self.assertLess(dur, 2.2)
        self.assertIsNotNone(latency.tracker.current())

    def test_timeout(self):
        rec = self.make()
        fake_sd.MIC["source"] = Scenario([])
        with self.assertRaises(sr.WaitTimeoutError):
            rec.listen(timeout=0.5)

    def test_wake_then_same_breath_command(self):
        det = wake_word.WakeWordDetector("fake", threshold=0.5, patience=2, log=lambda m: None)
        rec = self.make(wake=det)
        # "يا يوبي" (tone) at 0.3–0.9s, command speech right after, no pause
        fake_sd.MIC["source"] = Scenario([(0.3, 0.9, "wake"), (0.9, 1.9, "speech")])
        self.assertTrue(rec.wait_for_wake(hotkey_wakes=False, timeout=3))
        time.sleep(0.7)                       # Yobi plays the chime etc. — user keeps talking
        audio = rec.listen(timeout=3, phrase_time_limit=5)
        dur = len(audio.frame_data) / 2 / 16000
        self.assertGreater(dur, 0.8)         # the command that started BEFORE listen() was kept

    def test_set_hotkey_swaps_the_wake_key(self):
        import keyboard
        live, real = [], (keyboard.add_hotkey, keyboard.remove_hotkey)

        def add(key, cb):
            if key == "broken":
                raise ValueError(key)
            live.append(key)
        keyboard.add_hotkey, keyboard.remove_hotkey = add, live.remove      # no real key hook
        try:
            rec = self.make()
            self.assertTrue(rec.set_hotkey("ctrl+alt+y")); self.assertEqual(live, ["ctrl+alt+y"])
            self.assertTrue(rec.set_hotkey("f8")); self.assertEqual(live, ["f8"])
            self.assertFalse(rec.set_hotkey("broken")); self.assertEqual(live, ["f8"])     # the old key stays
            self.assertTrue(rec.set_hotkey("f8")); self.assertEqual(live, ["f8"])
        finally:
            keyboard.add_hotkey, keyboard.remove_hotkey = real

    def test_wake_by_key_only(self):
        det = wake_word.WakeWordDetector("fake", threshold=0.5, patience=2, log=lambda m: None)
        rec = self.make(wake=det)
        det.pause(True)                       # Settings → wake: key
        fake_sd.MIC["source"] = Scenario([(0.1, 0.9, "wake"), (0.9, 1.6, "speech")])
        self.assertFalse(rec.wait_for_key(timeout=1.8))   # saying "يا يوبي" does nothing
        self.assertFalse(det.event.is_set())
        self.assertIsNone(rec.pop_wake_candidate())        # and nothing is sent to Whisper
        self.assertLess(rec._frames.qsize(), 30)          # old audio doesn't pile up
        threading.Timer(0.2, rec._on_hotkey).start()
        self.assertTrue(rec.wait_for_key(timeout=1.0))
        self.assertFalse(rec.hotkey_event.is_set())

    def test_stale_wake_event_ignored(self):
        det = wake_word.WakeWordDetector("fake", log=lambda m: None)
        det.event.set(); det.last_time = time.time() - 30
        rec = self.make(wake=det)
        fake_sd.MIC["source"] = Scenario([])
        self.assertFalse(rec.wait_for_wake(hotkey_wakes=False, timeout=0.4))

    def test_full_duplex_barge_in_by_speech(self):
        speaking = {"on": True}; stopped = []
        rec = self.make(speaking=lambda: speaking["on"],
                        stop=lambda: (stopped.append(time.time()), speaking.update(on=False)))
        self.assertTrue(rec.full_duplex)
        fake_sd.MIC["source"] = Scenario([(0.6, 1.8, "loud")])
        audio = rec.listen(timeout=4, phrase_time_limit=5)
        self.assertTrue(stopped)
        dur = len(audio.frame_data) / 2 / 16000
        self.assertGreater(dur, 0.9)         # beginning of the interruption kept

    def test_own_voice_does_not_barge_in(self):
        """Yobi talking loud into the mic + AEC → no self-interruption."""
        fake_sd.MIC["echo_gain"] = 1.0
        speaking = {"on": True}; stopped = []
        rec = self.make(speaking=lambda: speaking["on"], stop=lambda: stopped.append(1))
        t = threading.Thread(target=lambda: self.eng.play(noise(48000 * 2, 9000).astype(np.int16), 48000), daemon=True)
        t.start()
        threading.Timer(2.2, lambda: speaking.update(on=False)).start()
        fake_sd.MIC["source"] = Scenario([])
        with self.assertRaises(sr.WaitTimeoutError):
            rec.listen(timeout=0.5)
        self.assertFalse(stopped)

    def test_no_speech_barge_in_during_unreferenced_playback(self):
        speaking = {"on": True}; stopped = []
        rec = self.make(speaking=lambda: speaking["on"], stop=lambda: stopped.append(1))
        audio_io.set_unreferenced(True)
        threading.Timer(1.8, lambda: (audio_io.set_unreferenced(False), speaking.update(on=False))).start()
        fake_sd.MIC["source"] = Scenario([(0.3, 1.5, "loud")])   # e.g. pygame playing Yobi's voice
        with self.assertRaises(sr.WaitTimeoutError):
            rec.listen(timeout=0.4)
        self.assertFalse(stopped)

    def test_wake_barge_in_while_speaking(self):
        det = wake_word.WakeWordDetector("fake", log=lambda m: None)
        speaking = {"on": True}; stopped = []
        rec = self.make(speaking=lambda: speaking["on"], wake=det, barge="wake",
                        stop=lambda: (stopped.append(1), speaking.update(on=False)))
        fake_sd.MIC["source"] = Scenario([(0.4, 1.0, "wake"), (1.0, 2.0, "speech")])
        audio = rec.listen(timeout=4, phrase_time_limit=5)
        self.assertTrue(stopped)
        self.assertGreater(len(audio.frame_data) / 2 / 16000, 0.8)


class TestLegacyMode(unittest.TestCase):
    """No AudioEngine (livekit/sounddevice output missing) → v3 behaviour."""
    def test_own_stream_listen_and_whisper_barge_fallback(self):
        fake_sd.MIC.update(source=Scenario([(0.3, 1.1, "speech")]), echo_gain=0.0)
        rec = audio_input.VADRecognizer(hotkey=None, engine=None, log=lambda m: None)
        self.assertFalse(rec.full_duplex); self.assertFalse(rec.has_wake_model)
        audio = rec.listen(timeout=3)
        self.assertGreater(len(audio.frame_data) / 2 / 16000, 0.6)
        rec._stream.stop()


class TestTTS(EngineCase):
    def test_edge_down_falls_back_to_piper_through_engine(self):
        import tts_engine as T
        with tempfile.TemporaryDirectory() as d:
            T.PREFS_PATH = os.path.join(d, "p.json")
            eng = T.TTSEngine()
            T._HAS_EDGE_TTS = True
            class FakePiper:
                available = True; model_path = "x"
                def synth(self, text): return (tone(300, 11025, 6000, sr_=22050).astype(np.int16), 22050)
                def configure(self, *a, **k): pass
            eng.piper = FakePiper()
            async def boom(text): raise ConnectionError("no internet")
            eng._synth_edge = boom
            logs = []
            latency.tracker.configure(log=logs.append); latency.tracker._csv = None
            latency.start_turn(); latency.mark("stt_done", info="groq-turbo")
            eng.speak("أهلا يا محمد")
            time.sleep(0.2); eng.wait_until_done(5)
            self.assertEqual(eng.last_backend, "piper")
            self.assertTrue(any("TTS أول صوت" in l for l in logs))
            heard = np.concatenate([c for _, c in list(fake_sd.SPEAKER)])
            self.assertGreater(np.abs(heard).max(), 3000)       # played via AudioEngine
            # cooldown: next sentence goes straight to piper (no Edge wait)
            t0 = time.time(); eng.speak("تاني"); time.sleep(0.05); eng.wait_until_done(5)
            self.assertEqual(eng.last_backend, "piper")
            eng.set_backend("piper")
            self.assertEqual(json.load(open(T.PREFS_PATH))["backend"], "piper")
            self.assertEqual(T.TTSEngine().backend, "piper")
            with self.assertRaises(ValueError):
                eng.set_backend("nope")

    def test_stop_cuts_engine_playback(self):
        import tts_engine as T
        with tempfile.TemporaryDirectory() as d:
            T.PREFS_PATH = os.path.join(d, "p.json")
            eng = T.TTSEngine()
            class FakePiper:
                available = True; model_path = "x"
                def synth(self, text): return (np.zeros(22050 * 5, np.int16) + 2000, 22050)
            eng.piper = FakePiper(); eng.set_backend("piper", save=False)
            T._HAS_EDGE_TTS = False
            eng.speak("جملة طويلة")
            time.sleep(0.6); self.assertTrue(eng.is_speaking())
            t0 = time.time(); eng.stop(); time.sleep(0.15)
            self.assertFalse(eng.is_speaking()); self.assertFalse(self.eng._speech.size)


class TestSounds(EngineCase):
    def test_chime_goes_through_engine(self):
        import sounds
        sounds.play_wake(); time.sleep(0.35)
        heard = np.concatenate([c for _, c in list(fake_sd.SPEAKER)[-40:]])
        self.assertGreater(np.abs(heard).max(), 3000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
