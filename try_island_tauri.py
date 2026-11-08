# -*- coding: utf-8 -*-
"""Try the new Tauri island on screen without starting Yobi:  python try_island_tauri.py

Shows the compact island (real music, downloads and mic/camera dots show up live), plays
Yobi's turn once (listening, thinking, working, done, a reply, a question you can click, a
mistake), then stays quiet so you can try the panel: hover it, or press Ctrl+Alt+I.
The menu's "جرّب الحالات" plays the turn again. Ctrl+C or closing the terminal stops it.
"""
import time

import electron_island as ei

if ei.find_tauri() is None:
    raise SystemExit("Build the Tauri island first: cd island-tauri && npx tauri build")

isl = ei.ElectronIsland(engine="tauri")


def picked(value):
    print("you picked:", value)


def turn():
    steps = [
        (0, lambda: isl._send({"t": "focus", "phase": "focus", "round": 1, "total": 4,
                               "ends_at": time.time() * 1000 + 18 * 60_000})),
        (5000, lambda: isl._send({"t": "focus", "phase": None})),
        (7000, lambda: isl.set_state("listening", "سامعك.. اتكلم 🎤")),
        (10000, lambda: isl.set_state("thinking", "بفكر في طلبك…")),
        (12500, lambda: (isl.set_state("executing", "بفتح Discord"), isl.set_progress(0.3))),
        (13500, lambda: isl.set_progress(0.7)),
        (14500, lambda: isl.set_state("success", "تمام، فتحت ديسكورد")),
        (19500, lambda: isl.say("الساعة ١٠:٤٥ بالليل. لو هتلعب كمان، اشرب مياه الأول 💧", state="info")),
        (27000, lambda: isl.ask("قصدك Euro Truck Simulator 2 ولا Rocket League؟",
                                [("Euro Truck Simulator 2", "ets2"), ("Rocket League", "rl"),
                                 ("لا، ولا حاجة", "none")], picked, timeout_ms=12000)),
        (41000, lambda: isl.set_state("error", "مش لاقي البرنامج ده على الجهاز")),
        # a few notices (interface 6); the real ones come from Yobi's services as their time comes
        (50000, lambda: isl._send({"t": "notice", "kind": "brief", "greet": "صباح الفل 🌞",
                                   "weather": {"temp": 23, "code": 2, "hi": 27}})),
        (66000, lambda: isl._send({"t": "notice", "kind": "download_done", "id": "try", "name": "movie.mkv", "size": 734e6})),
        (77000, lambda: isl._send({"t": "notice", "kind": "smart", "what": "math", "value": "35 × 35 + 20", "result": 1245})),
        (85000, lambda: isl._send({"t": "notice", "kind": "reminder", "sub": "ayah", "text": "أَلَا بِذِكْرِ ٱللَّهِ تَطْمَئِنُّ ٱلْقُلُوبُ",
                                   "ref": "الرعد ٢٨", "seconds": 20})),
    ]
    for ms, fn in steps:
        isl.after(ms, fn)


print("The island is at the top of the screen. Hover it (a quarter second) or press Ctrl+Alt+I.")
isl.after(1500, turn)
try:
    isl.mainloop()
except KeyboardInterrupt:
    isl.quit()
