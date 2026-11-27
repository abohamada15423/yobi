# -*- coding: utf-8 -*-
"""
Train models/ya_yobi.onnx: the small network openWakeWord runs on its speech features.

The real recordings carry the training (a fixed share of every batch), generated voices add other
speakers, and 2000 hours of other audio teach it what is not the call. `gen` and a fast `feats` need
Linux + GPU; README.md has the Colab steps. Each stage keeps its output in --work, so a stage can be rerun.

  python train_wake.py gen   --work w --piper-model en_US-libritts_r-medium.pt
  python train_wake.py feats --work w --real real --bg esc50 music --rir impulses
  python train_wake.py train --work w --acav acav.npy --fp-val validation_set_features.npy --out ya_yobi.onnx
  python train_wake.py score --work w --fp-val validation_set_features.npy --models old.onnx ya_yobi.onnx
  python train_wake.py eval  --real real --models old.onnx ya_yobi.onnx
"""
import argparse
import copy
import glob
import os

import numpy as np

SR, N = 16000, 32000      # a 2 s window = the 16 feature frames an openWakeWord model reads
POSITIVE = ["ya yobi", "yaa yoobi", "ya yoobee"]      # the voices are English, so it is spelled as it sounds
NEAR = ["ya yousef", "ya bibi", "ya habibi", "yo baby", "jubilee", "you be", "yoga", "ya robi", "ya bob",
        "hobby", "yobs", "ya", "yeah", "ya baba", "ya mama", "toby", "ya ruby", "ya gobi", "nairobi",
        "wasabi", "yalla", "yalla bina", "ya rab", "ya salam", "ya basha", "ya sahbi", "ya ibni", "ya abu",
        "ya yahya", "ya younes", "you bet", "you beat", "yo bro", "ya boy", "yellow bee", "yeah okay",
        "yeah obviously", "your baby", "euro", "ya toota", "youtube", "you too", "ya youtube", "open youtube",
        "ya yo", "yo yo", "ya yaba", "ya yomi", "ya loli", "yeah totally", "ya zobi", "ya dobi", "ya nobi"]
THR = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


# ------------------------------------------------------------------ audio
def files(*dirs):
    return sorted(f for d in dirs for ext in ("wav", "flac")
                  for f in glob.glob(os.path.join(d, "**", "*." + ext), recursive=True))


def load(path):
    import soundfile as sf
    from scipy.signal import resample_poly
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if sr != SR:
        g = int(np.gcd(sr, SR))
        x = resample_poly(x, SR // g, sr // g).astype(np.float32)
    return x


def rms(x):
    return float(np.sqrt(np.mean(x ** 2)) + 1e-9)


def trim(x):
    """Cut the silence around speech, so the end of the phrase can be put where we want it."""
    f = 320
    n = len(x) // f
    if n < 3:
        return x
    level = np.sqrt((x[:n * f].reshape(n, f) ** 2).mean(axis=1))
    on = np.flatnonzero(level > max(0.1 * level.max(), 1e-4))
    if not len(on):
        return x
    return x[max(0, on[0] * f - 480):min(len(x), (on[-1] + 1) * f + 960)]


def phrase(x):
    """The call inside a real recording: the loudest stretch that stands out above the room (gaps under 0.2 s
    bridged). trim() is not enough here: a key click sets its level, and it cut most calls to under half a second.
    None when nothing stands out or the length is not that of a call, so the clip cannot be placed and is left out."""
    x = np.trim_zeros(x)                        # the recorder pads with digital silence
    f = 160
    n = len(x) // f
    if n < 20:
        return None
    db = 10 * np.log10((x[:n * f].reshape(n, f) ** 2).mean(axis=1) + 1e-12)
    db = np.convolve(np.pad(db, 2, mode="edge"), np.ones(5) / 5, "valid")
    floor, peak = np.percentile(db, 15), np.percentile(db, 97)
    if peak - floor < 9:
        return None
    on = np.flatnonzero(db > floor + max(6.0, 0.35 * (peak - floor)))
    if not len(on):
        return None
    g = max(np.split(on, np.flatnonzero(np.diff(on) > 20) + 1), key=lambda g: (10 ** (db[g] / 10)).sum())
    c = x[max(0, g[0] * f - 960):min(len(x), (g[-1] + 1) * f + 1280)]
    return c if 0.35 * SR <= len(c) <= 1.5 * SR else None


class Maker:
    """Turns clips into 2 s training windows: speed, echo, loudness, something said just before, background."""

    def __init__(self, rng, room, other, rirs, leads):
        self.rng, self.room, self.other, self.rirs, self.leads = rng, room, other, rirs, leads

    def pick(self, pool):
        return pool[self.rng.integers(len(pool))]

    def crop(self, x):
        if len(x) < N:
            x = np.tile(x, N // len(x) + 1)
        i = self.rng.integers(len(x) - N + 1)
        return x[i:i + N]

    def background(self):                       # -> (sound, how many dB quieter than the speech)
        r = self.rng.random()
        if self.room and r < 0.5:
            return self.crop(self.pick(self.room)), self.rng.uniform(5, 35)
        if self.other and r < 0.85:
            return self.crop(self.pick(self.other)), self.rng.uniform(3, 25)
        hiss = self.rng.standard_normal(N).astype(np.float32)
        if self.rng.random() < 0.5:             # rumble instead of hiss
            hiss = np.cumsum(hiss)
            hiss -= hiss.mean()
        return hiss, self.rng.uniform(10, 40)

    def speech(self, clip, max_jitter=0.3):
        """The clip ends up to max_jitter seconds before the window end: where it sits when the model must fire."""
        from scipy.signal import fftconvolve
        rng, c = self.rng, clip
        if len(c) > N:
            c = self.crop(c)
        if rng.random() < 0.7:
            k = rng.uniform(0.9, 1.1)
            c = np.interp(np.arange(0, len(c) - 1, k), np.arange(len(c)), c).astype(np.float32)
        if self.rirs and rng.random() < 0.35:
            c = fftconvolve(c, self.pick(self.rirs))[:len(c) + 2400].astype(np.float32)
        end = N - int(rng.uniform(0, max_jitter) * SR)
        c = c[-end:]
        level = 10 ** (rng.uniform(-38, -14) / 20)
        w = np.zeros(N, np.float32)
        w[end - len(c):end] = c * (level / rms(c))
        stop = end - len(c) - int(rng.uniform(0.05, 0.3) * SR)
        if self.leads and stop > 4800 and rng.random() < 0.2:
            lead = self.pick(self.leads)[-stop:]
            w[stop - len(lead):stop] += lead * (level * rng.uniform(0.4, 1.0) / rms(lead))
        if rng.random() < 0.85:
            b, quieter = self.background()
            w += b * (level / 10 ** (quieter / 20) / rms(b))
        else:
            w += rng.standard_normal(N).astype(np.float32) * 10 ** (-75 / 20)
        return w

    def noise(self, clip):
        b = self.crop(clip)
        return b * (10 ** (self.rng.uniform(-50, -15) / 20) / rms(b))

    def partial(self, clip):                    # «يا» and the start of the name only: must not fire
        return self.speech(clip[:int(len(clip) * self.rng.uniform(0.3, 0.5))])


def feature_models():
    """openWakeWord's shared feature models, downloaded once."""
    import openwakeword
    from openwakeword.utils import download_models
    res = os.path.join(os.path.dirname(openwakeword.__file__), "resources", "models")
    if not os.path.exists(os.path.join(res, "embedding_model.onnx")):
        download_models(["none"])               # a name that matches no wake model: feature models only


def features():
    import onnxruntime as ort
    from openwakeword.utils import AudioFeatures
    feature_models()
    try:
        import torch  # noqa: F401  brings in the CUDA libraries onnxruntime-gpu looks for
    except ImportError:
        pass
    gpu = "CUDAExecutionProvider" in ort.get_available_providers()
    F = AudioFeatures(device="gpu" if gpu else "cpu")
    ncpu = 1 if "CUDA" in F.onnx_execution_provider else (os.cpu_count() or 2)
    print("features on", F.onnx_execution_provider, flush=True)

    def embed(windows):
        x = (np.clip(np.stack(windows), -1, 1) * 32767).astype(np.int16)
        out = F.embed_clips(x, batch_size=256, ncpu=ncpu).astype(np.float32)
        assert out.shape[1:] == (16, 96), out.shape
        return out
    return embed


# ------------------------------------------------------------------ stages
def gen(a):
    from piper_sample_generator.__main__ import generate_samples
    for name, texts in (("positive", POSITIVE), ("near", NEAR)):
        out = os.path.join(a.work, "synth", name)
        os.makedirs(out, exist_ok=True)
        if len(os.listdir(out)) < a.n_synth:
            generate_samples(text=texts, output_dir=out, model=a.piper_model, max_samples=a.n_synth, batch_size=50,
                             slerp_weights=(0.5, 0.75, 1.0), length_scales=(0.75, 1.0, 1.25),
                             noise_scales=(0.667, 0.85, 1.0), noise_scale_ws=(0.8, 1.0))
        print(name, len(os.listdir(out)), "clips", flush=True)


def feats(a):
    rng = np.random.default_rng(0)
    embed = features()

    def real(split, name):
        return [load(f) for f in files(os.path.join(a.real, split, name))]

    def synth(name):
        xs = [trim(load(f)) for f in files(os.path.join(a.work, "synth", name))]
        return [x for i, x in enumerate(xs) if i % 10], xs[::10]        # every 10th is validation

    rirs = []
    for f in files(*a.rir)[:300]:
        r = load(f)
        r = r[int(np.argmax(np.abs(r))):][:SR]
        rirs.append(r / np.sqrt((r ** 2).sum() + 1e-9))
    bg = files(*a.bg)
    other = []
    for f in bg[::max(1, len(bg) // 1500)]:
        try:
            other.append(load(f))
        except Exception as e:                  # one broken file in a public set must not stop the run
            print("skipped", f, e)
    other_tr, other_te = [x for i, x in enumerate(other) if i % 10], other[::10]
    pos_tr, pos_te = ([c for c in map(phrase, real(split, "positive")) if c is not None] for split in ("train", "test"))
    sp_tr, sp_te = real("train", "speech"), real("test", "speech")
    room_tr, room_te = real("train", "room"), real("test", "room")
    spos_tr, spos_te = synth("positive")
    near_tr, near_te = synth("near")
    print(f"real: {len(pos_tr)}+{len(pos_te)} calls, {len(sp_tr)}+{len(sp_te)} speech, {len(room_tr)}+{len(room_te)} room | "
          f"generated: {len(spos_tr)}+{len(spos_te)} calls, {len(near_tr)}+{len(near_te)} near | "
          f"background {len(other)}, echoes {len(rirs)}", flush=True)
    tr = Maker(rng, room_tr, other_tr, rirs, [trim(x) for x in sp_tr] + near_tr)
    te = Maker(rng, room_te, other_te, rirs, [trim(x) for x in sp_te] + near_te)
    s = a.scale
    plan = [        # name, clips, windows per clip, how
        ("pos_real", pos_tr, 60 * s, tr.speech), ("pos_synth", spos_tr, 2 * s, tr.speech),
        ("neg_near", near_tr, 1 * s, tr.speech), ("neg_speech", sp_tr, 30 * s, lambda c: tr.speech(c, 0.6)),
        ("neg_room", room_tr, 60 * s, tr.noise), ("neg_partial", pos_tr, 12 * s, tr.partial),
        ("neg_partial_synth", spos_tr, 0.3 * s, tr.partial), ("neg_bg", other_tr, 3 * s, tr.noise),
        ("val_pos_real", pos_te, 30 * s, te.speech), ("val_pos_synth", spos_te, 1 * s, te.speech),
        ("val_neg_near", near_te, 1 * s, te.speech), ("val_neg_speech", sp_te, 20 * s, lambda c: te.speech(c, 0.6)),
        ("val_neg_room", room_te, 30 * s, te.noise),
    ]
    out = {}
    for name, clips, per, how in plan:
        n = int(round(len(clips) * per))
        parts = [embed([how(clips[j % len(clips)]) for j in range(i, min(n, i + 512))]) for i in range(0, n, 512)]
        out[name] = np.concatenate(parts) if parts else np.zeros((0, 16, 96), np.float32)
        print(f"{name}: {len(out[name])} windows", flush=True)
    out["neg_partial"] = np.concatenate([out["neg_partial"], out.pop("neg_partial_synth")])
    os.makedirs(a.work, exist_ok=True)
    np.savez(os.path.join(a.work, "feats.npz"), **out)


def net(layer, blocks):
    """The same shape of network as the openWakeWord trainer makes, so Yobi loads it like any wake model."""
    from torch import nn
    body = [nn.Flatten(), nn.Linear(16 * 96, layer), nn.LayerNorm(layer), nn.ReLU()]
    for _ in range(blocks):
        body += [nn.Linear(layer, layer), nn.LayerNorm(layer), nn.ReLU()]
    return nn.Sequential(*body, nn.Linear(layer, 1), nn.Sigmoid())


def false_wakes(p, thr, row=1, gap=25):
    """Wakes on audio with no call in it: `row` frames in a row over the threshold (wake_patience in Yobi),
    and a new one only after 2 s of quiet, like its cooldown."""
    hit = np.flatnonzero(np.convolve(p >= thr, np.ones(row, int), "valid") == row)
    return 0 if not len(hit) else 1 + int((np.diff(hit) > gap).sum())


def run(m, x):
    import torch
    with torch.no_grad():
        return torch.cat([m(x[i:i + 16384]).squeeze(1) for i in range(0, len(x), 16384)]).cpu().numpy()


def onnx_score(path):
    """Scores from a saved model, one window at a time, the way openWakeWord runs it."""
    import onnxruntime as ort
    s = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    name = s.get_inputs()[0].name
    assert s.get_inputs()[0].shape[1:] == [16, 96] and s.get_outputs()[0].shape[-1] == 1, "not a wake model shape"

    def score(v):
        return np.array([s.run(None, {name: f[None]})[0].ravel()[0]
                         for i in range(0, len(v), 8192) for f in v[i:i + 8192].cpu().numpy()])
    return score


def validation(a, dev):
    """What every model is judged on: held-out windows of real and generated clips, and ~11 h of other audio."""
    import torch
    d = np.load(os.path.join(a.work, "feats.npz"))
    T = {k: torch.from_numpy(d[k]).to(dev) for k in d.files}
    val = torch.from_numpy(np.load(a.fp_val).astype(np.float32)).to(dev) if a.fp_val else None
    hours = len(val) * 0.08 / 3600 if val is not None else 0

    def check(score):                           # score(x) -> probabilities; x is (n, 16, 96)
        r = {k: score(T[k]) for k in T if k.startswith("val_") and len(T[k])}
        if val is not None:
            r["other"] = score(val.unfold(0, 16, 1).permute(0, 2, 1))
        return r

    def row(r, thr):
        neg = np.concatenate([r[k] for k in ("val_neg_speech", "val_neg_room") if k in r] or [np.zeros(1)])
        return {"real": float((r["val_pos_real"] >= thr).mean()),
                "synth": float((r["val_pos_synth"] >= thr).mean()) if "val_pos_synth" in r else float("nan"),
                "room": float((neg >= thr).mean()),
                "near": float((r["val_neg_near"] >= thr).mean()) if "val_neg_near" in r else float("nan"),
                "per_hour": false_wakes(r["other"], thr) / hours if hours else float("nan"),
                "per_hour2": false_wakes(r["other"], thr, 2) / hours if hours else float("nan")}

    def budget(r):
        """The lowest threshold that keeps false wakes on other audio inside the budget, and the scores there.
        It may sit very close to 1: train() then moves the model so that this point becomes 0.5."""
        for z in np.arange(-4, 13.01, 0.25):
            t = float(1 / (1 + np.exp(-z)))
            q = row(r, t)
            if not hours or q["per_hour"] <= a.target:
                return t, q
        return 1.0, q

    def table(r, title):
        print(f"\n{title}\n thr  real calls  generated calls  real speech+room  near-misses  false wakes/h (other audio)  with 2 in a row")
        for t in THR + (0.99, 0.999):
            q = row(r, t)
            print(f" {t:<5}  {q['real']:7.1%}  {q['synth']:14.1%}  {q['room']:15.2%}  {q['near']:10.2%}  {q['per_hour']:10.2f}"
                  f"  {q['per_hour2']:25.2f}")
        t = budget(r)[0]
        print(f"inside the budget of {a.target} false wakes/h from threshold {t:.5f}" if t < 1 else
              f"over the budget of {a.target} false wakes/h at every threshold", flush=True)
    return T, hours, check, row, budget, table


def train(a):
    import torch
    import torch.nn.functional as fn
    torch.manual_seed(0)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    T, hours, check, row, budget, table = validation(a, dev)
    acav = np.load(a.acav, mmap_mode="r") if a.acav else None
    if acav is not None:
        acav = acav[:a.acav_limit or None]      # a part that fits in memory reads far faster than the whole file
        print("other audio:", acav.shape, acav.dtype, f"| false-wake check: {hours:.1f} h", flush=True)
    share = {"pos_real": 64, "pos_synth": 64, "neg_near": 64, "neg_speech": 64, "neg_room": 32, "neg_partial": 24, "neg_bg": 32}
    share = {k: n for k, n in share.items() if len(T.get(k, ())) and k not in a.drop}
    model = net(a.layer, a.blocks).to(dev)
    opt = torch.optim.Adam(model.parameters(), lr=a.lr)
    judged = copy.deepcopy(model) if a.ema else model       # a running average of the weights: steadier than any one step

    warm, hold, ptr = a.steps // 5, a.steps // 3, int(np.random.default_rng(0).integers(1 << 20))
    best, loss = None, torch.zeros(())
    checks = set(np.linspace(a.steps * 0.4, a.steps, 31).astype(int).tolist())
    for step in range(1, a.steps + 1):
        lr = a.lr * step / warm if step < warm else a.lr if step < warm + hold else \
            0.5 * a.lr * (1 + np.cos(np.pi * (step - warm - hold) / (a.steps - warm - hold)))
        for g in opt.param_groups:
            g["lr"] = lr
        xs, ys = [], []
        for k, n in share.items():
            xs.append(T[k][torch.randint(len(T[k]), (n,), device=dev)])
            ys.append(torch.full((n,), float(k.startswith("pos")), device=dev))
        if acav is not None:
            ptr = ptr % (len(acav) - 1024)
            xs.append(torch.from_numpy(np.asarray(acav[ptr:ptr + 1024], dtype=np.float32)).to(dev))
            ys.append(torch.zeros(1024, device=dev))
            ptr += 1024
        x, y = torch.cat(xs), torch.cat(ys)
        p = model(x).squeeze(1)
        hard = ((y == 0) & (p >= 0.001)) | ((y == 1) & (p < 0.999))     # as openWakeWord: skip what it already knows
        if hard.any():
            w = torch.ones_like(y)
            w[y == 0] = 1 + (a.neg_weight - 1) * step / a.steps          # a false wake costs more and more
            loss = fn.binary_cross_entropy(p[hard], y[hard], weight=w[hard])
            opt.zero_grad()
            loss.backward()
            opt.step()
            if a.ema:
                with torch.no_grad():
                    for avg, now in zip(judged.parameters(), model.parameters()):
                        avg.lerp_(now, 1 - a.ema)
        if step in checks:
            r = check(lambda v: run(judged, v))
            t, q = budget(r)
            # real calls heard at the threshold the false-wake budget allows; over budget everywhere: fewest false wakes
            key = q["real"] - 10 * q["room"] if t < 1 else -1 - q["per_hour"]
            if best is None or key > best[0]:
                best = (key, step, {k: v.detach().clone() for k, v in judged.state_dict().items()}, t)
            h = row(r, 0.5)
            print(f"step {step}: loss {loss.item():.4f} | at 0.5: real {h['real']:.1%}, generated {h['synth']:.1%}, "
                  f"false wakes/h {h['per_hour']:.2f} | budget threshold {t:.5f}: real {q['real']:.1%}, generated {q['synth']:.1%}, "
                  f"real speech+room {q['room']:.2%}, false wakes/h {q['per_hour']:.2f}{' *' if best[1] == step else ''}", flush=True)
    model.load_state_dict(best[2])
    model.eval()
    torch.save(best[2], os.path.splitext(a.out)[0] + ".pt")     # export can be redone without training again
    print("\nkept step", best[1])
    table(check(lambda v: run(model, v)), "new model, as trained")
    if best[3] < 1:                             # move the scores so the budget point is the usual threshold, 0.5
        with torch.no_grad():
            model[-2].bias -= float(np.log(best[3] / (1 - best[3])))
        table(check(lambda v: run(model, v)), f"new model, as saved: 0.5 is where it was {best[3]:.5f}")

    cpu = model.cpu()
    dummy = torch.rand(1, 16, 96)
    try:
        torch.onnx.export(cpu, dummy, a.out, opset_version=13, dynamo=False)
    except Exception as e:                      # a torch without the old exporter (or without its switch)
        print("old exporter failed:", e)
        torch.onnx.export(cpu, dummy, a.out)
    probe = T["val_pos_real"][:50].cpu()
    gap = np.abs(onnx_score(a.out)(probe) - run(cpu, probe)).max()
    assert gap < 1e-3, f"the saved model differs from the trained one by {gap}"
    print(f"saved {a.out} ({os.path.getsize(a.out) / 1e3:.0f} kB), same scores as the trained network")


def score(a):
    """The same table for saved models, to compare an old one with a new one."""
    T, hours, check, row, budget, table = validation(a, "cpu")
    for path in a.models:
        table(check(onnx_score(path)), path)


def evaluate(a):
    """Play the real clips to each model the way Yobi does, 80 ms at a time, and count the clips it fires on:
    with one frame over the threshold, and with two in a row (wake_patience 2)."""
    from openwakeword.model import Model
    feature_models()
    rng = np.random.default_rng(0)

    def quiet(n):                               # a quiet room, not digital zero
        return rng.integers(-40, 40, n).astype(np.int16)
    for path in a.models:
        m = Model(wakeword_models=[path], inference_framework="onnx")
        print(f"\n{path}\n{'clips':20s}    n  " + " ".join(f">={t}" for t in THR) + "  median")
        for split in ("test", "train"):
            for name in ("positive", "speech", "room"):
                fs = files(os.path.join(a.real, split, name))
                one, two = [], []
                for f in fs:
                    x = np.concatenate([quiet(16000), (load(f) * 32767).astype(np.int16), quiet(24000)])
                    m.reset()
                    s = np.array([max(m.predict(x[i:i + 1280]).values()) for i in range(0, len(x) - 1279, 1280)])
                    one.append(s.max())
                    two.append(np.minimum(s[:-1], s[1:]).max())
                for label, peaks in ((split + "/" + name, np.array(one)), ("  2 in a row", np.array(two))):
                    print(f"{label:20s} {len(peaks):4d}  " + " ".join(f"{int((peaks >= t).sum()):5d}" for t in THR)
                          + f"  {np.median(peaks):.2f}")
                if name != "positive":          # which clips set it off: worth a listen, one may be a call
                    fired = [f"{os.path.basename(f)} {p:.2f}" for f, p in zip(fs, one) if p >= 0.5]
                    if fired:
                        print("   fires on:", ", ".join(fired[:12]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["gen", "feats", "train", "score", "eval"])
    ap.add_argument("--work", default="wake_work")
    ap.add_argument("--real", default="real")
    ap.add_argument("--piper-model", default="en_US-libritts_r-medium.pt")
    ap.add_argument("--n-synth", type=int, default=6000)
    ap.add_argument("--bg", nargs="*", default=[], help="folders of other sounds (music, noises) to mix in")
    ap.add_argument("--rir", nargs="*", default=[], help="folders of room echoes")
    ap.add_argument("--scale", type=float, default=1.0, help="fewer windows per clip, for a quick trial")
    ap.add_argument("--acav", default=None, help="openwakeword_features_ACAV100M_2000_hrs_16bit.npy")
    ap.add_argument("--acav-limit", type=int, default=0, help="use only the first N windows of --acav (0 = all)")
    ap.add_argument("--fp-val", default=None, help="validation_set_features.npy")
    ap.add_argument("--steps", type=int, default=40000)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--layer", type=int, default=128)
    ap.add_argument("--blocks", type=int, default=1)
    ap.add_argument("--neg-weight", type=float, default=600)
    ap.add_argument("--ema", type=float, default=0.999, help="how much of the averaged weights to keep each step (0 = off)")
    ap.add_argument("--target", type=float, default=2, help="false wakes per hour allowed on the other-audio check")
    ap.add_argument("--out", default="ya_yobi.onnx")
    ap.add_argument("--drop", nargs="*", default=[], help="training groups to leave out, e.g. neg_partial")
    ap.add_argument("--models", nargs="*", default=[])
    a = ap.parse_args()
    {"gen": gen, "feats": feats, "train": train, "score": score, "eval": evaluate}[a.stage](a)


if __name__ == "__main__":
    main()
