"""Build a vertical Short from a spec.

Steps: download source, cut and frame each segment at 1080x1920, record the
narration, lay out captions, hook, location card and outcome card, mix audio,
then run the sync, loudness and dead-air checks. Writes build.json and a render
frame sheet next to the spec. The MP4 goes to the GitHub release "renders".

Usage:
  python pipeline/build.py                 # build every Short that needs it
  python pipeline/build.py <short_id> ...  # build specific Shorts
  python pipeline/build.py --local ...     # do not upload to the release
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import traceback
from pathlib import Path

import numpy as np
import requests
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (CANDIDATES, FONTS, ROOT, SHORTS, WORK, config, ffprobe, iso, load_json, media_duration,  # noqa: E402
                    run, save_json, short_dirs, short_state)

W, H, FPS = 1080, 1920, 30
SR = 48000
GAP = 0.22          # pause between narration lines
LEAD = 0.05         # narration starts this soon
TAIL = 0.7          # outcome card holds this long after the last word (short, so the loop restarts fast)
FG_SHIFT = -110     # fit layout: footage sits a little above center
RELEASE_TAG = "renders"

# ---------------------------------------------------------------- narration


class Voice:
    def __init__(self, cfg):
        self.cfg = cfg
        self.engine = os.environ.get("CCF_TTS", cfg.get("engine", "kokoro"))
        self.k = None

    def _kokoro(self):
        if self.k is None:
            from kokoro_onnx import Kokoro
            mdir = Path(os.environ.get("KOKORO_DIR", Path.home() / ".cache" / "kokoro"))
            self.k = Kokoro(str(mdir / "kokoro-v1.0.onnx"), str(mdir / "voices-v1.0.bin"))
        return self.k

    def _eleven(self, text, dest, prev_text=None, next_text=None):
        vid = self.cfg["voice_id"]
        body = {
            "text": text,
            "model_id": self.cfg.get("model_id", "eleven_multilingual_v2"),
            "voice_settings": self.cfg.get("voice_settings") or {
                "stability": 0.45, "similarity_boost": 0.8, "style": 0.15, "use_speaker_boost": True,
                "speed": float(self.cfg.get("speed", 1.0))},
        }
        if prev_text:
            body["previous_text"] = prev_text
        if next_text:
            body["next_text"] = next_text
        for attempt in range(4):
            r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{vid}",
                              params={"output_format": "mp3_44100_128"},
                              headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "Content-Type": "application/json"},
                              json=body, timeout=120)
            if r.status_code == 429 or r.status_code >= 500:
                import time
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code != 200:
                raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:300]}")
            break
        mp3 = Path(str(dest) + ".mp3")
        mp3.write_bytes(r.content)
        raw = Path(str(dest) + ".raw.wav")
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", mp3, "-ar", SR, "-ac", 1, raw])
        x, sr = sf.read(raw, dtype="float32")
        sf.write(dest, trim_silence(x, sr, thresh=0.006), sr)
        mp3.unlink()
        raw.unlink()
        return media_duration(dest)

    def full_take(self, lines, work):
        """Whole script in one ElevenLabs request with character timing.

        Returns (wav_path, per-line list of word timings in seconds)."""
        import base64
        allowed = {t.lower() for t in self.cfg.get("allowed_tags", [])}
        def keep_tags(t):
            t = TAG_RE.sub(lambda m: m.group(0) if m.group(0)[1:-1].strip().lower() in allowed else " ", t)
            return re.sub(r"\s+", " ", t).strip()
        spoken = [keep_tags(speakable(l)) for l in lines]
        full = " ".join(spoken)
        settings = self.cfg.get("voice_settings") or {"stability": 0.45, "similarity_boost": 0.8}
        body = {"text": full, "model_id": self.cfg.get("model_id", "eleven_v4"), "voice_settings": settings}
        key = hashlib.md5(json.dumps([self.cfg["voice_id"], body], sort_keys=True).encode()).hexdigest()
        cache = WORK / "tts_cache" / f"{key}.json"
        if cache.exists():
            j = json.loads(cache.read_text())
            return self._from_take(j, full, spoken, work)
        r = None
        for attempt in range(4):
            r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{self.cfg['voice_id']}/with-timestamps",
                              params={"output_format": "mp3_44100_128"},
                              headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"],
                                       "Content-Type": "application/json"},
                              json=body, timeout=180)
            if r.status_code == 429 or r.status_code >= 500:
                import time
                time.sleep(5 * (attempt + 1))
                continue
            break
        if r.status_code != 200:
            raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:300]}")
        j = r.json()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(j))
        return self._from_take(j, full, spoken, work)

    def _from_take(self, j, full, spoken, work):
        import base64
        mp3 = work / "voice_full.mp3"
        mp3.write_bytes(base64.b64decode(j["audio_base64"]))
        wav = work / "voice_full.wav"
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", mp3, "-ar", SR, "-ac", 1, wav])
        al = j.get("alignment") or j.get("normalized_alignment") or {}
        chars = al.get("characters") or []
        st = al.get("character_start_times_seconds") or []
        en = al.get("character_end_times_seconds") or []
        # map each character of our text to an alignment index by walking both strings
        amap, k = [None] * len(full), 0
        for i, ch in enumerate(full):
            look = k
            while look < len(chars) and look < k + 40 and chars[look] != ch:
                look += 1
            if look < len(chars) and chars[look] == ch:
                amap[i] = look
                k = look + 1
        dur = media_duration(wav)

        def t_at(i, end=False):
            for d in range(0, 60):
                for idx in ((i - d, i + d) if not end else (i + d, i - d)):
                    if 0 <= idx < len(full) and amap[idx] is not None:
                        return (en if end else st)[amap[idx]]
            return None

        out, offset = [], 0
        for line in spoken:
            words = []
            for a, b in word_spans(line):
                ws, we = t_at(offset + a), t_at(offset + b - 1, end=True)
                words.append([ws, we])
            offset += len(line) + 1
            out.append(words)
        # fill any gaps by interpolation
        flat = [w for line in out for w in line]
        for idx, w in enumerate(flat):
            if w[0] is None:
                w[0] = flat[idx - 1][1] if idx else 0.0
            if w[1] is None or w[1] < w[0]:
                w[1] = min(w[0] + 0.3, dur)
        return wav, out

    def say(self, text, dest, prev_text=None, next_text=None):
        """Write a 48 kHz mono wav for one line and return its duration."""
        text = speakable(text)
        if self.engine == "elevenlabs":
            return self._eleven(text, dest, prev_text and speakable(prev_text), next_text and speakable(next_text))
        if self.engine == "test":
            dur = max(0.8, len(text.split()) / 2.6)
            t = np.linspace(0, dur, int(SR * dur), endpoint=False)
            audio = 0.2 * np.sin(2 * np.pi * 180 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))
            sf.write(dest, audio.astype(np.float32), SR)
            return dur
        samples, sr = self._kokoro().create(text, voice=self.cfg["voice"], speed=float(self.cfg.get("speed", 1.0)),
                                            lang="en-us")
        samples = trim_silence(np.asarray(samples, dtype=np.float32), sr)
        tmp = Path(str(dest) + ".raw.wav")
        sf.write(tmp, samples, sr)
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", tmp, "-ar", SR, "-ac", 1, dest])
        tmp.unlink()
        return media_duration(dest)


def trim_silence(x, sr, thresh=0.01, pad=0.04):
    idx = np.where(np.abs(x) > thresh)[0]
    if idx.size == 0:
        return x
    a = max(idx[0] - int(pad * sr), 0)
    b = min(idx[-1] + int(pad * sr), len(x))
    return x[a:b]


NUM_WORDS = {"MH-60": "M H sixty", "MH-65": "M H sixty-five", "HC-130": "H C one thirty", "HH-60": "H H sixty",
             "C-130": "C one thirty", "F/A-18": "F A eighteen", "F-35": "F thirty-five", "USCGC": "Coast Guard Cutter"}


def speakable(text):
    """Small fixes so the voice reads aircraft names and units naturally."""
    for k, v in NUM_WORDS.items():
        text = text.replace(k, v)
    text = re.sub(r"\bmph\b", "miles per hour", text)
    text = re.sub(r"\bft\b", "feet", text)
    text = re.sub(r"\bnm\b", "nautical miles", text)
    return text


# ---------------------------------------------------------------- source and footage


TAG_RE = re.compile(r"\[[^\]\n]{1,60}\]")


def strip_tags(text):
    """Remove ElevenLabs audio tags like [tense] for captions and on-screen text."""
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", text or "")).strip()


def word_spans(text):
    """(start, end) character spans of words in text, skipping audio tags."""
    spans, i = [], 0
    for m in re.finditer(r"\[[^\]\n]{1,60}\]|\S+", text):
        if not m.group(0).startswith("["):
            spans.append((m.start(), m.end()))
    return spans


def fetch_source(cand):
    src = cand["source_file"]["src"]
    dest = WORK / "src" / (cand["id"] + ".mp4")
    if dest.exists() and dest.stat().st_size > 10000:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(src, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return dest


def has_audio(path):
    return any(s["codec_type"] == "audio" for s in ffprobe(path)["streams"])


def video_size(path):
    v = next(s for s in ffprobe(path)["streams"] if s["codec_type"] == "video")
    w, h = int(v["width"]), int(v["height"])
    rot = int((v.get("tags") or {}).get("rotate", 0) or 0)
    for sd in v.get("side_data_list") or []:
        if "rotation" in sd:
            rot = int(sd["rotation"])
    if abs(rot) in (90, 270):
        w, h = h, w
    return w, h


def detect_crop(src, a, b):
    """Find black bars baked into this stretch of footage; returns 'w:h:x:y' or None."""
    found = []
    span = max(b - a, 0.5)
    for frac in (0.2, 0.5, 0.8):
        t = a + span * frac
        res = run(["ffmpeg", "-hide_banner", "-ss", f"{max(t - 0.5, 0):.2f}", "-i", src, "-t", 1,
                   "-vf", "cropdetect=limit=24:round=2:reset=0", "-an", "-f", "null", "-"], check=False)
        m = re.findall(r"crop=(\d+:\d+:\d+:\d+)", res.stderr or "")
        if m:
            found.append(m[-1])
    if not found:
        return None
    best = max(set(found), key=found.count)
    w, h, _, _ = map(int, best.split(":"))
    return best if w > 64 and h > 64 else None


def segment_filter(seg, sw, sh, crop=None):
    zoom = float(seg.get("zoom", 1.0))
    speed = float(seg.get("speed", 1.0))
    layout = seg.get("layout", "auto")
    portrait = sh > sw
    if layout == "auto":
        layout = "crop" if portrait else "fit"
    pts = (f"crop={crop}," if crop else "") + f"setpts=(PTS-STARTPTS)/{speed}"
    if layout == "crop":
        cx = float(seg.get("crop_x", 0.5))
        sh2 = int(H * zoom)
        vf = (f"{pts},scale=-2:{sh2},crop={W}:{H}:x='(iw-{W})*{cx}':y='(ih-{H})/2',"
              f"setsar=1,fps={FPS},format=yuv420p")
    else:
        fw = int(W * zoom) // 2 * 2
        vf = (f"{pts},split[a][b];"
              f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=28:3,"
              f"eq=brightness=-0.16:saturation=0.8[bg];"
              f"[b]scale={fw}:-2[fg];"
              f"[bg][fg]overlay=x=(W-w)/2:y=(H-h)/2+({FG_SHIFT}),setsar=1,fps={FPS},format=yuv420p")
    af = f"asetpts=PTS-STARTPTS,{atempo(speed)}aresample={SR},aformat=channel_layouts=stereo"
    return vf, af


def atempo(speed):
    if abs(speed - 1.0) < 1e-3:
        return ""
    parts, s = [], speed
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    parts.append(f"atempo={s:.4f}")
    return ",".join(parts) + ","


def cut_segments(src, segments, work):
    fw, fh = video_size(src)
    audio = has_audio(src)
    parts = []
    for i, seg in enumerate(segments):
        out = work / f"seg{i:02d}.mp4"
        crop = detect_crop(src, float(seg["start"]), float(seg["end"]))
        sw, sh = fw, fh
        if crop:
            cw, ch, _, _ = map(int, crop.split(":"))
            if cw >= fw - 8 and ch >= fh - 8:
                crop = None
            else:
                sw, sh = cw, ch
        vf, af = segment_filter(seg, sw, sh, crop)
        a, b = float(seg["start"]), float(seg["end"])
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", a, "-to", b, "-i", src]
        if not audio:
            cmd += ["-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=stereo"]
        fc = f"[0:v]{vf}[v];" + (f"[0:a]{af}[a]" if audio else f"[1:a]{af}[a]")
        cmd += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-shortest",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "pcm_s16le", out]
        run(cmd)
        parts.append(out)
    lst = work / "concat.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    joined = work / "footage.mkv"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", 0, "-i", lst, "-c", "copy",
         joined])
    return joined, (fw, fh), audio


# ---------------------------------------------------------------- text layout (ASS)


def ass_color(hex_rgb, alpha=0):
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def ass_time(t):
    t = max(t, 0)
    hh = int(t // 3600)
    mm = int(t % 3600 // 60)
    ss = t % 60
    return f"{hh}:{mm:02d}:{ss:05.2f}"


def esc(text):
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def chunk_words(line, max_words=3, max_chars=18):
    words = line.split()
    chunks, cur = [], []
    for w in words:
        trial = " ".join(cur + [w])
        if cur and (len(cur) >= max_words or len(trial) > max_chars):
            chunks.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
        # end a chunk at sentence or clause punctuation
        if re.search(r"[.,;:!?]$", w) and len(cur) >= 1:
            chunks.append(" ".join(cur))
            cur = []
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def build_ass(spec, timeline, total, credit_line=None):
    """Minimal text: captions, a brief location tag, and a compact outcome panel."""
    orange = ass_color("#FF5A1F")
    white = ass_color("#FFFFFF")
    black = ass_color("#000000")
    ink = ass_color("#0B0E12", 0x55)
    styles = [
        # name, font, size, primary, outline colour, back, bold, borderstyle, outline, shadow, align, mL, mR, mV
        ("Cap", "Anton", 86, white, black, ass_color("#000000", 0x90), 0, 1, 5, 2, 2, 90, 90, 560),
        ("Loc", "Inter", 34, white, ink, black, 1, 3, 10, 0, 8, 120, 120, 210),
        ("OutLabel", "Anton", 50, orange, black, black, 0, 1, 0, 0, 7, 0, 0, 0),
        ("OutText", "Inter", 54, white, black, black, 1, 1, 0, 0, 7, 0, 0, 0),
        ("Box", "Inter", 20, black, black, black, 0, 1, 0, 0, 7, 0, 0, 0),
    ]
    out = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0",
           "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
           "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
           "MarginL, MarginR, MarginV, Encoding"]
    for (n, f, sz, pc, oc, bc, bold, bs, o, sh, al, ml, mr, mv) in styles:
        out.append(f"Style: {n},{f},{sz},{pc},{pc},{oc},{bc},{-1 if bold else 0},0,0,0,100,100,0,0,{bs},{o},{sh},"
                   f"{al},{ml},{mr},{mv},1")
    out += ["", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]

    caps = []

    def ev(layer, a, b, style, text):
        if style == "Cap":
            caps.append([a, b, text])
            return
        out.append(f"Dialogue: {layer},{ass_time(a)},{ass_time(b)},{style},,0,0,0,,{text}")

    outcome_start = timeline[-1]["start"]
    lc = spec["location_card"]
    ev(3, 0.2, min(2.8, outcome_start - 0.3), "Loc", r"{\fad(150,250)}" + esc(f"{lc['place']}  |  {lc['date']}".upper()))
    for item in timeline[:-1]:
        words = item["words"]
        groups, cur = [], []
        for wd in words:
            trial = " ".join(x["w"] for x in cur + [wd])
            if cur and (len(cur) >= 3 or len(trial) > 18):
                groups.append(cur)
                cur = []
            cur.append(wd)
            if re.search(r"[.,;:!?]$", wd["w"]):
                groups.append(cur)
                cur = []
        if cur:
            groups.append(cur)
        for gi, g in enumerate(groups):
            g_end = g[-1]["e"]
            nxt = groups[gi + 1][0]["s"] if gi + 1 < len(groups) else item["end"] + 0.25
            g_end = max(g_end, min(nxt, g_end + 0.35))
            for wi, wd in enumerate(g):
                a = wd["s"] if wi else g[0]["s"]
                b = g[wi + 1]["s"] if wi + 1 < len(g) else g_end
                parts = []
                for wj, other in enumerate(g):
                    t = esc(other["w"].upper())
                    parts.append(r"{\1c" + orange + "&}" + t + r"{\1c" + white + "&}" if wj == wi else t)
                pop = r"{\fscx92\fscy92\t(0,70,\fscx100\fscy100)}" if wi == 0 else ""
                ev(1, a, b, "Cap", pop + " ".join(parts))
    caps.sort(key=lambda c: c[0])
    for i, (a, b, text) in enumerate(caps):
        if i + 1 < len(caps):
            b = min(b, caps[i + 1][0])
        if b - a > 0.02:
            out.append(f"Dialogue: 1,{ass_time(a)},{ass_time(b)},Cap,,0,0,0,,{text}")
    # Outcome: a compact panel in the lower middle, footage stays visible above it
    lines = wrap(esc(strip_tags(spec["outcome"])), 30)
    n = lines.count(r"\N") + 1
    top = 1000
    height = 70 + 66 * n + 40
    a, b = outcome_start - 0.05, total
    ev(4, a, b, "Box", r"{\an7\pos(60," + str(top) + r")\1c&H0B0E12&\1a&H38&\fad(200,0)\p1}"
       + f"m 0 0 l 960 0 960 {height} 0 {height}" + r"{\p0}")
    ev(5, a, b, "Box", r"{\an7\pos(60," + str(top) + r")\1c" + orange + r"&\1a&H00&\fad(200,0)\p1}"
       + f"m 0 0 l 10 0 10 {height} 0 {height}" + r"{\p0}")
    ev(5, a, b, "OutLabel", r"{\an7\pos(100," + str(top + 22) + r")\fad(200,0)}HOW IT ENDED")
    ev(5, a, b, "OutText", r"{\an7\pos(100," + str(top + 92) + r")\q2\fad(250,0)}" + lines)
    return "\n".join(out) + "\n"


def wrap(text, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return r"\N".join(lines)


# ---------------------------------------------------------------- audio


def narration_track(spec, voice, work):
    lines = list(spec["narration"]) + [spec["outcome"]]
    timeline = []
    if voice.engine == "elevenlabs" and voice.cfg.get("single_take", True):
        wav, word_times = voice.full_take(lines, work)
        x, sr = sf.read(wav, dtype="float32")
        if x.ndim > 1:
            x = x.mean(axis=1)
        last_end = 0.0
        for text, times in zip(lines, word_times):
            cap_words = strip_tags(text).split()
            spoken_n = len(times)
            if spoken_n and len(cap_words) == spoken_n:
                words = [{"w": w, "s": LEAD + a, "e": LEAD + b} for w, (a, b) in zip(cap_words, times)]
            else:  # spoken form differs (e.g. MH-60 read as M H sixty): spread caption words over the line
                a = LEAD + (times[0][0] if times else last_end)
                b = LEAD + (times[-1][1] if times else last_end + 1)
                wts = [max(len(w), 2) for w in cap_words] or [1]
                t, words = a, []
                for w, wt in zip(cap_words, wts):
                    d = (b - a) * wt / sum(wts)
                    words.append({"w": w, "s": t, "e": t + d})
                    t += d
            for wd in words:  # keep times moving forward so captions never overlap
                wd["s"] = max(wd["s"], LEAD + last_end)
                wd["e"] = max(wd["e"], wd["s"] + 0.08)
                last_end = wd["e"] - LEAD
            timeline.append({"text": strip_tags(text), "start": round(words[0]["s"], 3) if words else last_end,
                             "end": round(words[-1]["e"], 3) if words else last_end,
                             "words": [{k: (round(v, 3) if k != "w" else v) for k, v in wd.items()} for wd in words]})
        total = max(timeline[-1]["end"] + TAIL, LEAD + len(x) / sr + 0.2)
        buf = np.zeros(int(SR * (total + 0.5)), dtype=np.float32)
        a = int(LEAD * SR)
        buf[a:a + len(x)] += x[: len(buf) - a]
        voice_wav = work / "voice.wav"
        sf.write(voice_wav, buf, SR)
        return voice_wav, timeline, round(total, 3)

    t = LEAD
    clips = []
    for i, text in enumerate(lines):
        wav = work / f"line{i:02d}.wav"
        d = voice.say(strip_tags(text) if voice.engine != "elevenlabs" else text, wav,
                      prev_text=" ".join(lines[:i])[-400:] or None,
                      next_text=lines[i + 1] if i + 1 < len(lines) else None)
        cap = strip_tags(text).split()
        wts = [max(len(w), 2) for w in cap] or [1]
        tt, words = t, []
        for w, wt in zip(cap, wts):
            dd = d * wt / sum(wts)
            words.append({"w": w, "s": round(tt, 3), "e": round(tt + dd, 3)})
            tt += dd
        timeline.append({"text": strip_tags(text), "start": round(t, 3), "end": round(t + d, 3), "words": words})
        clips.append((t, wav))
        t += d + GAP
    total = timeline[-1]["end"] + TAIL
    buf = np.zeros(int(SR * (total + 0.5)), dtype=np.float32)
    for start, wav in clips:
        x, sr = sf.read(wav, dtype="float32")
        if x.ndim > 1:
            x = x.mean(axis=1)
        a = int(start * SR)
        buf[a:a + len(x)] += x[: len(buf) - a]
    voice_wav = work / "voice.wav"
    sf.write(voice_wav, buf, SR)
    return voice_wav, timeline, round(total, 3)


def pick_music():
    files = sorted((ROOT / "assets" / "music").glob("*.mp3")) + sorted((ROOT / "assets" / "music").glob("*.m4a"))
    return files


# ---------------------------------------------------------------- checks


def measure(path):
    res = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-filter_complex", "ebur128=peak=true", "-f", "null",
               "-"], check=False)
    err = res.stderr or ""
    summary = err[err.rfind("Summary:"):]
    i = re.search(r"I:\s+(-?[0-9.]+) LUFS", summary)
    p = re.search(r"Peak:\s+(-?[0-9.]+|-inf) dBFS", summary)
    return (float(i.group(1)) if i else None), (float(p.group(1)) if p and p.group(1) != "-inf" else None)


def silences(path, noise="-45dB", d=1.0):
    res = run(["ffmpeg", "-hide_banner", "-i", path, "-af", f"silencedetect=noise={noise}:d={d}", "-f", "null", "-"],
              check=False)
    starts = [float(x) for x in re.findall(r"silence_start: (-?[0-9.]+)", res.stderr or "")]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", res.stderr or "")]
    return list(zip(starts, ends + [None] * (len(starts) - len(ends))))


def blacks(path):
    res = run(["ffmpeg", "-hide_banner", "-i", path, "-vf", "blackdetect=d=0.4:pix_th=0.06", "-an", "-f", "null", "-"],
              check=False)
    return re.findall(r"black_start:([0-9.]+) black_end:([0-9.]+)", res.stderr or "")


def freezes(path):
    res = run(["ffmpeg", "-hide_banner", "-i", path, "-vf", "freezedetect=n=0.002:d=2.5", "-an", "-f", "null", "-"],
              check=False)
    return re.findall(r"freeze_start: ([0-9.]+)", res.stderr or "")


def run_checks(out, total, timeline):
    info = ffprobe(out)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    vd = float(v.get("duration") or info["format"]["duration"])
    ad = float(a.get("duration") or 0) if a else 0
    lufs, peak = measure(out)
    sil = silences(out)
    blk = blacks(out)
    frz = freezes(out)
    checks = {
        "resolution": {"ok": (int(v["width"]), int(v["height"])) == (W, H), "value": f"{v['width']}x{v['height']}"},
        "duration": {"ok": 12 <= vd <= 59.5, "value": round(vd, 2)},
        "av_sync": {"ok": a is not None and abs(vd - ad) < 0.15, "value": round(vd - ad, 3)},
        "fits_narration": {"ok": vd >= timeline[-1]["end"] + 0.3, "value": round(vd - timeline[-1]["end"], 2)},
        "loudness": {"ok": lufs is not None and -15.5 <= lufs <= -12.5, "value": lufs},
        "true_peak": {"ok": peak is not None and peak <= -0.8, "value": peak},
        "dead_air": {"ok": not sil, "value": [[round(s, 2), round(e, 2) if e else None] for s, e in sil]},
        "starts_talking": {"ok": timeline[0]["start"] <= 0.3, "value": timeline[0]["start"]},
        "black_frames": {"ok": not blk, "value": blk},
        "frozen_frames": {"ok": True, "warn": bool(frz), "value": frz},
    }
    return checks


def render_sheet(out, dest, total, timeline):
    times = [0.3, 1.5, 3.0] + [total * f for f in (0.25, 0.4, 0.55, 0.7)] + \
            [timeline[-1]["start"] - 0.8, timeline[-1]["start"] + 0.6, total - 0.2]
    tiles = []
    tmp = WORK / "rsheet"
    tmp.mkdir(parents=True, exist_ok=True)
    for i, t in enumerate(times):
        f = tmp / f"{i}.jpg"
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{max(t, 0):.2f}", "-i", out, "-frames:v", 1,
             "-vf", "scale=270:480", f], check=False)
        if f.exists():
            tiles.append((t, Image.open(f).convert("RGB")))
    cols = 5
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 270, rows * 480), (17, 20, 24))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(str(FONTS / "Inter-Variable.ttf"), 18)
    for i, (t, img) in enumerate(tiles):
        x, y = (i % cols) * 270, (i // cols) * 480
        sheet.paste(img, (x, y))
        draw.rectangle([x, y, x + 64, y + 24], fill=(255, 90, 31))
        draw.text((x + 5, y + 2), f"{t:.1f}s", fill="white", font=font)
    sheet.save(dest, quality=78)


# ---------------------------------------------------------------- main build


def credit_line_for(cand):
    branch = cand.get("branch") or ""
    who = {"Coast Guard": "U.S. Coast Guard", "Navy": "U.S. Navy", "Army": "U.S. Army", "Air Force": "U.S. Air Force",
           "Marines": "U.S. Marine Corps", "Space Force": "U.S. Space Force"}.get(branch, cand.get("unit_name") or "DVIDS")
    return f"FOOTAGE: {who.upper()} VIA DVIDS"


def build_one(d, voice_cfg, cfg, upload=True):
    spec = load_json(d / "spec.json")
    sid = spec["short_id"]
    cand = load_json(CANDIDATES / f"{spec['candidate_id']}.json")
    work = WORK / sid
    work.mkdir(parents=True, exist_ok=True)
    voice = Voice(voice_cfg)

    src = fetch_source(cand)
    footage, (sw, sh), src_audio = cut_segments(src, spec["segments"], work)
    voice_wav, timeline, total = narration_track(spec, voice, work)
    fdur = media_duration(footage)
    if fdur < total - 0.05:
        raise RuntimeError(f"footage is {fdur:.1f}s but the narration needs {total:.1f}s; add or lengthen segments")

    ass = work / "overlay.ass"
    ass.write_text(build_ass(spec, timeline, total, spec.get("credit_overlay") or credit_line_for(cand)))

    keep_src = spec.get("keep_source_audio", True) and src_audio
    src_db = float(cfg.get("source_audio_db_under_voice", -16))
    music = pick_music()
    inputs = ["-i", footage, "-i", voice_wav]
    if music:
        pick = music[int(hashlib.md5(sid.encode()).hexdigest(), 16) % len(music)]
        inputs += ["-stream_loop", "-1", "-i", pick]
    fontsdir = str(FONTS).replace(":", r"\:")
    fc = [f"[0:v]trim=0:{total},setpts=PTS-STARTPTS,subtitles='{ass}':fontsdir='{fontsdir}'[v]",
          f"[1:a]atrim=0:{total},asetpts=PTS-STARTPTS,aformat=channel_layouts=stereo,"
          f"loudnorm=I=-16:TP=-2:LRA=7,asplit=3[vo][sc1][sc2]"]
    beds = []
    if keep_src:
        fc.append(f"[0:a]atrim=0:{total},asetpts=PTS-STARTPTS,loudnorm=I={-16 + src_db}:TP=-6:LRA=11[srcn]")
        fc.append("[srcn][sc1]sidechaincompress=threshold=0.02:ratio=6:attack=15:release=350[src]")
        beds.append("[src]")
    if music:
        mdb = float(cfg.get("music_db_below_voice", 14))
        fc.append(f"[2:a]atrim=0:{total},asetpts=PTS-STARTPTS,aformat=channel_layouts=stereo,"
                  f"loudnorm=I={-16 - mdb}:TP=-8:LRA=7,afade=t=out:st={max(total - 1.2, 0)}:d=1.2[mus0]")
        fc.append("[mus0][sc2]sidechaincompress=threshold=0.02:ratio=4:attack=20:release=400[mus]")
        beds.append("[mus]")
    else:
        fc.append("[sc2]anullsink")
    if not keep_src:
        fc.append("[sc1]anullsink")
    mix_in = "[vo]" + "".join(beds)
    fc.append(f"{mix_in}amix=inputs={1 + len(beds)}:normalize=0:duration=first,"
              f"loudnorm=I=-14:TP=-1.5:LRA=11,aresample={SR}[a]")
    out = work / f"{sid}.mp4"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs, "-filter_complex", ";".join(fc),
         "-map", "[v]", "-map", "[a]", "-t", total, "-r", FPS,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-profile:v", "high", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-ar", SR, "-movflags", "+faststart", out])

    checks = run_checks(out, total, timeline)
    sheet = d / "render_sheet.jpg"
    render_sheet(out, sheet, total, timeline)
    ok = all(c["ok"] for c in checks.values())
    asset_url = None
    if ok and upload:
        asset_url = publish_render(out, f"{sid}-r{spec.get('revision', 1)}.mp4")
    result = {
        "short_id": sid,
        "revision": spec.get("revision", 1),
        "status": "ok" if ok else "checks_failed",
        "built_at": iso(),
        "duration": total,
        "source_resolution": f"{sw}x{sh}",
        "timeline": [{k: v for k, v in t.items() if k != "wav"} for t in timeline],
        "checks": checks,
        "failed_checks": [k for k, c in checks.items() if not c["ok"]],
        "render_sheet": f"data/shorts/{sid}/render_sheet.jpg",
        "asset_url": asset_url,
        "local_path": str(out),
    }
    save_json(d / "build.json", result)
    return result


def publish_render(path, name):
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        return None
    if subprocess.run(["gh", "release", "view", RELEASE_TAG], capture_output=True).returncode != 0:
        run(["gh", "release", "create", RELEASE_TAG, "--title", "Rendered Shorts",
             "--notes", "Rendered Shorts waiting for QA and upload. Built automatically."])
    named = path.with_name(name)
    if named != path:
        named.write_bytes(path.read_bytes())
    run(["gh", "release", "upload", RELEASE_TAG, named, "--clobber"])
    return f"https://github.com/{repo}/releases/download/{RELEASE_TAG}/{name}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--max", type=int, default=16)
    args = ap.parse_args()
    cfg = config()
    dirs = [SHORTS / i for i in args.ids] if args.ids else [d for d in short_dirs() if short_state(d) == "needs_build"]
    dirs = dirs[: args.max]
    print(f"{len(dirs)} to build")
    failures = 0
    for d in dirs:
        try:
            r = build_one(d, cfg["voice"], cfg, upload=not args.local)
            print(f"{d.name}: {r['status']} {r['duration']}s failed={r['failed_checks']}")
        except Exception as e:
            failures += 1
            spec = load_json(d / "spec.json") or {}
            save_json(d / "build.json", {"short_id": d.name, "revision": spec.get("revision", 1), "status": "error",
                                         "built_at": iso(), "error": str(e)[-1500:]})
            print(f"{d.name}: ERROR {e}")
            traceback.print_exc()
    print(json.dumps({"built": len(dirs), "errors": failures}))


if __name__ == "__main__":
    main()
