# -*- coding: utf-8 -*-
"""What goes into the friends' build: only files git tracks (so nothing personal — .gitignore
keeps out .env, config.json, recordings, chat history, learned commands...), minus dev-only files,
plus the few untracked assets Yobi needs to run."""
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEV_ONLY = {".gitignore", "config.hearing.example.json", "requirements.txt"}
DEV_DIRS = ("island-tauri/", "docs/", "tests/", "tools/", "packaging/", "backups/")
# untracked on purpose (.gitignore) but needed: the offline "يا يوبي" model.
# NOT models/intent_model.*: it was trained on this PC's apps and would pick them for a friend's words.
EXTRA = ["models/ya_yobi.onnx"] + [
    # the hearing model trained on Yobi's commands (tools/finetune_whisper.py); agent.py uses it for "small"
    "models/yobi-whisper/" + f for f in ("model.bin", "config.json", "preprocessor_config.json", "tokenizer.json", "vocabulary.json")]
# personal files that must never be in a build, checked again after copying
NEVER = {".env", "config.json", "chat_history.json", "companion_data.json", "game_stats.json",
         "learned_commands.json", "learning_data.json", "usage_patterns.json", "vocab.json",
         "installed_apps_cache.json", "smart_scan_cache.json", "login_calibration.json",
         "session_summaries.json", "island_state.json", "ui_prefs.json", ".yobi_runtime.json",
         "latency_log.csv", "yobi.log", "shelf.json", "intent_model.joblib", "intent_model.json", "local_brain.joblib"}


def app_files():
    # tracked files + new files not committed yet (.gitignore still keeps personal ones out)
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    files = [f for f in out.splitlines()
             if f not in DEV_ONLY and not f.startswith(DEV_DIRS) and not f.startswith("README")]
    files = [f for f in dict.fromkeys(files) if os.path.basename(f) not in NEVER and os.path.exists(os.path.join(ROOT, f))]
    return files + [f for f in EXTRA if os.path.exists(os.path.join(ROOT, f))]


if __name__ == "__main__":
    for f in app_files():
        print(f)
