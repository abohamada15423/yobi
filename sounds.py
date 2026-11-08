# -*- coding: utf-8 -*-
"""
Sound Effects — أصوات تأكيد وخطأ ليوبي.

v3: when the shared AudioEngine is running, chimes are soft sine tones
played through it, so the echo canceller removes them from the mic
(the wake chime no longer leaks into your command). Otherwise: winsound
beeps exactly like before.

Public API:
    play_wake() / play_success() / play_error() / play_listening() / play_hide()
"""

import threading

try:
    import winsound
except ImportError:  # pragma: no cover
    winsound = None

try:
    import audio_io
except Exception:  # pragma: no cover
    audio_io = None


def _engine():
    if audio_io is None:
        return None
    eng = audio_io.get_audio_engine()
    return eng if (eng is not None and eng.has_output) else None


def _play_sequence_async(notes):
    eng = _engine()
    if eng is not None:
        try:
            pcm = audio_io.tone([f for f, _ in notes], [d for _, d in notes])
            eng.play_fx(pcm, audio_io.OUT_SR)
            return
        except Exception:
            pass
    if winsound is None:
        return

    def _run():
        for freq, dur in notes:
            try:
                winsound.Beep(freq, dur)
            except Exception:
                return
    threading.Thread(target=_run, daemon=True).start()


def _play_async(freq, duration_ms):
    _play_sequence_async([(freq, duration_ms)])


def play_wake():
    """Two-tone ascending chime — wake word recognised."""
    _play_sequence_async([(880, 80), (1320, 120)])


def play_success():
    """Quick positive ding — command succeeded."""
    _play_sequence_async([(1047, 70), (1319, 70), (1568, 100)])


def play_error():
    """Low double buzz — something went wrong."""
    _play_sequence_async([(330, 150), (262, 200)])


def play_listening():
    """Subtle single tick — mic is active."""
    _play_async(1200, 50)


def play_hide():
    """Descending tone — island collapsing / conversation ending."""
    _play_sequence_async([(880, 60), (660, 80)])
