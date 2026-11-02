"""Preview every planned shot of a spec exactly as the build will crop it, before building.

Usage: python3 pipeline/preview_shots.py data/shorts/<id>/spec.json [more specs]

Writes data/shorts/<id>/shot_preview.jpg (one row per shot, a frame every 0.5 s, with the
vertical crop applied) and prints warnings for the problems QA rejects most:
  EMPTY   frames that are mostly flat sky, water, sand or a fade (nothing to look at)
  DARK    frames that are mostly black
  REUSED  shots that overlap source seconds already used earlier in the Short
Fix every warning before pushing: move the shot, change crop_x, or pick another moment.
"""
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CANDIDATES, FONTS, load_json, run  # noqa: E402
import build  # noqa: E402

TW, TH = 108, 192   # thumbnail size (9:16)
STEP = 0.5          # seconds between sampled frames


def frame_flags(img):
    """EMPTY when almost nothing stands out from the background colour (open water, sky, sand, murk)."""
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    g = a.mean(-1)
    med = np.median(a.reshape(-1, 3), axis=0)
    standout = float((np.sqrt(((a - med) ** 2).sum(-1)) > 55).mean())
    flags = []
    if float((g < 35).mean()) > 0.7:
        flags.append("DARK")
    elif standout < 0.12:
        flags.append("EMPTY")
    return flags, standout


def shot_frames(src, seg, sw, sh, crop, tmp, tag):
    vf, _ = build.segment_filter(dict(seg), sw, sh, crop)
    a, b = float(seg["start"]), float(seg["end"])
    out = tmp / f"{tag}_%03d.png"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", a, "-to", b, "-i", src,
         "-filter_complex", f"[0:v]{vf},fps={1 / STEP},scale={TW}:{TH}[v]", "-map", "[v]", out])
    return sorted(tmp.glob(f"{tag}_*.png"))


def preview(spec_path):
    spec_path = Path(spec_path)
    spec = load_json(spec_path)
    cand = load_json(CANDIDATES / f"{spec['candidate_id']}.json")
    src = build.fetch_source(cand)
    fw, fh = build.video_size(src)
    lines = spec.get("line_shots") or []
    rows, warnings, used = [], [], []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for li, shots in enumerate(lines):
            label_line = f"L{li + 1}" if li < len(lines) - 1 else "OUT"
            for si, seg in enumerate(shots):
                a, b = float(seg["start"]), float(seg["end"])
                for (ua, ub, who) in used:
                    if min(b, ub) - max(a, ua) > 0.3:
                        warnings.append(f"{label_line} shot {si + 1} ({a}-{b}s) REUSED: overlaps {who} ({ua}-{ub}s)")
                used.append((a, b, f"{label_line} shot {si + 1}"))
                crop = build.detect_crop(src, a, b)
                sw, sh = fw, fh
                if crop:
                    cw, ch, _, _ = map(int, crop.split(":"))
                    if cw >= fw - 8 and ch >= fh - 8:
                        crop = None
                    else:
                        sw, sh = cw, ch
                frames = shot_frames(src, seg, sw, sh, crop, tmp, f"{li:02d}_{si:02d}")
                imgs, bad = [], []
                for k, f in enumerate(frames):
                    im = Image.open(f).convert("RGB")
                    flags, _ = frame_flags(im)
                    imgs.append((im, flags, a + k * STEP))
                    if flags:
                        bad.append((a + k * STEP, flags[0]))
                if bad:
                    share = len(bad) / max(len(frames), 1)
                    if share >= 0.4:
                        kinds = sorted({k for _, k in bad})
                        warnings.append(f"{label_line} shot {si + 1} ({a}-{b}s): {'/'.join(kinds)} in {len(bad)} of "
                                        f"{len(frames)} frames, from {bad[0][0]:.1f}s")
                rows.append((f"{label_line} s{si + 1}  {a:.1f}-{b:.1f}s  {seg.get('layout', 'auto')} x={seg.get('crop_x', 0.5)}",
                             imgs))
    font = ImageFont.truetype(str(FONTS / "Inter-Bold.ttf"), 14) if (FONTS / "Inter-Bold.ttf").exists() else ImageFont.load_default()
    cols = max((len(r[1]) for r in rows), default=1)
    cols = min(cols, 14)
    sheet = Image.new("RGB", (cols * (TW + 4) + 4, len(rows) * (TH + 26) + 4), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    for ri, (label, imgs) in enumerate(rows):
        y = 4 + ri * (TH + 26)
        d.text((6, y), label, fill="white", font=font)
        for ci, (im, flags, t) in enumerate(imgs[:cols]):
            x = 4 + ci * (TW + 4)
            sheet.paste(im, (x, y + 22))
            if flags:
                d.rectangle([x, y + 22, x + TW - 1, y + 22 + TH - 1], outline=(255, 60, 60), width=3)
                d.text((x + 4, y + 26), flags[0], fill=(255, 80, 80), font=font)
    dest = spec_path.parent / "shot_preview.jpg"
    sheet.save(dest, quality=80)
    print(f"{spec_path.parent.name}: wrote {dest}")
    for w in warnings:
        print("  WARN", w)
    if not warnings:
        print("  no empty, dark or reused shots found")
    return warnings


if __name__ == "__main__":
    bad = 0
    for p in sys.argv[1:]:
        bad += len(preview(p))
    sys.exit(1 if bad else 0)
