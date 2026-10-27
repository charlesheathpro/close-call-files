"""Harvest new public-domain videos from DVIDS into data/candidates.

For every new asset it stores metadata, a transcript, scene-cut times and a
labeled frame sheet. Video files are never committed; the build downloads the
source fresh.
"""
import argparse
import os
import re
import sys
import time
from datetime import timedelta
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (CANDIDATES, DATA, FONTS, WORK, config, copyright_flags, iso, load_json,  # noqa: E402
                    media_duration, now_utc, run, safe_id, save_json)

API = "https://api.dvidshub.net"
SEEN = DATA / "seen.json"


def api_get(path, params):
    key = os.environ.get("DVIDS_API_KEY")
    if not key:
        sys.exit("DVIDS_API_KEY is not set")
    params = dict(params, api_key=key)
    headers = {"User-Agent": "close-call-files-harvester/1.0"}
    origin = os.environ.get("DVIDS_ORIGIN")
    if origin:
        headers["Referer"] = origin
        headers["Origin"] = origin
    for attempt in range(4):
        r = requests.get(API + path, params=params, headers=headers, timeout=60)
        if r.status_code == 503:
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code == 403:
            sys.exit("DVIDS returned 403: the API key is missing, invalid, or tied to another origin")
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def search(query, since, cfg):
    params = {
        "type[]": "video",
        "q": query["q"],
        "from_publishdate": since,
        "from_duration": cfg["min_duration"],
        "to_duration": cfg["max_duration"],
        "sort": "publishdate",
        "sortdir": "desc",
        "max_results": 50,
        "categories_exclude[]": cfg["exclude_categories"],
    }
    if query.get("branch"):
        params["branch"] = query["branch"]
    data = api_get("/search", params)
    return data.get("results", [])


def asset(asset_id):
    return api_get("/asset", {"id": asset_id}).get("results", {})


def pick_files(files):
    """Best file for the final build plus a small one for analysis."""
    mp4 = [f for f in files or [] if f.get("src") and "mp4" in (f.get("type") or "mp4")]
    if not mp4:
        return None, None
    def h(f):
        return min(int(f.get("height") or 0), int(f.get("width") or 0)) or int(f.get("height") or 0)
    # Final: highest resolution up to 1080 short side, highest bitrate within that.
    good = [f for f in mp4 if h(f) <= 1080] or mp4
    best = max(good, key=lambda f: (h(f), int(f.get("bitrate") or 0)))
    small = [f for f in mp4 if 300 <= h(f) <= 480] or [min(mp4, key=lambda f: int(f.get("size") or 0))]
    analysis = min(small, key=lambda f: int(f.get("size") or 0))
    return best, analysis


def download(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return dest


def srt_to_segments(text):
    segs = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.strip().splitlines()
        tl = next((l for l in lines if "-->" in l), None)
        if not tl:
            continue
        a, b = [x.strip().replace(",", ".") for x in tl.split("-->")]
        def secs(t):
            hh, mm, ss = t.split(":")
            return int(hh) * 3600 + int(mm) * 60 + float(ss)
        body = " ".join(l for l in lines[lines.index(tl) + 1:]).strip()
        if body:
            segs.append({"s": round(secs(a), 2), "e": round(secs(b), 2), "text": body})
    return segs


_whisper = None


def transcribe(video):
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        _whisper = WhisperModel(os.environ.get("WHISPER_MODEL", "base.en"), device="cpu", compute_type="int8")
    segments, _ = _whisper.transcribe(str(video), vad_filter=True, beam_size=1)
    out = []
    for s in segments:
        t = s.text.strip()
        if t:
            out.append({"s": round(s.start, 2), "e": round(s.end, 2), "text": t})
    return out


def scene_cuts(video):
    res = run(["ffmpeg", "-hide_banner", "-i", str(video), "-filter:v", "select='gt(scene,0.32)',showinfo",
               "-an", "-f", "null", "-"], check=False)
    times = [round(float(m), 2) for m in re.findall(r"pts_time:([0-9.]+)", res.stderr or "")]
    return times[:200]


def loud_spans(video):
    """Rough audio activity: list of [start, end] where audio is above -35 dB."""
    res = run(["ffmpeg", "-hide_banner", "-i", str(video), "-af", "silencedetect=noise=-35dB:d=0.6", "-f", "null", "-"],
              check=False)
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", res.stderr or "")]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", res.stderr or "")]
    return {"silence_starts": [round(x, 1) for x in starts[:100]], "silence_ends": [round(x, 1) for x in ends[:100]]}


def frame_sheet(video, dest, duration, start=0.0, n=16, cols=4, width=360):
    """Grid of n labeled frames spread across the clip."""
    tmp = WORK / "frames"
    tmp.mkdir(parents=True, exist_ok=True)
    for f in tmp.glob("*.jpg"):
        f.unlink()
    span = max(duration - start - 0.5, 1)
    times = [round(start + span * (i + 0.5) / n, 2) for i in range(n)]
    tiles = []
    for i, t in enumerate(times):
        out = tmp / f"{i:02d}.jpg"
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(t), "-i", str(video), "-frames:v", "1",
             "-vf", f"scale={width}:-2", str(out)], check=False)
        if out.exists():
            tiles.append((t, Image.open(out).convert("RGB")))
    if not tiles:
        return None
    tw, th = tiles[0][1].size
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * th), (17, 20, 24))
    font = ImageFont.truetype(str(FONTS / "Inter-Variable.ttf"), 18)
    draw = ImageDraw.Draw(sheet)
    for i, (t, img) in enumerate(tiles):
        x, y = (i % cols) * tw, (i // cols) * th
        sheet.paste(img, (x, y))
        label = f"{int(t // 60)}:{t % 60:04.1f}"
        draw.rectangle([x, y, x + 78, y + 26], fill=(255, 90, 31))
        draw.text((x + 6, y + 3), label, fill="white", font=font)
    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest, quality=72)
    return times


def credit_text(credit):
    if isinstance(credit, list):
        parts = []
        for c in credit:
            name = " ".join(x for x in [c.get("rank"), c.get("name")] if x)
            if name:
                parts.append(name)
        return ", ".join(parts) or "Courtesy"
    return credit or "Courtesy"


def process(asset_id, lane, query):
    a = asset(asset_id)
    if not a:
        return None, "asset lookup empty"
    flags = copyright_flags(a.get("title"), a.get("description"), a.get("keywords"), credit_text(a.get("credit")))
    if flags:
        return None, "copyright flags: " + ", ".join(flags)
    best, small = pick_files(a.get("files"))
    if not best:
        return None, "no mp4 files"
    work = WORK / safe_id(asset_id)
    work.mkdir(parents=True, exist_ok=True)
    vid = download(small["src"], work / "analysis.mp4")
    duration = media_duration(vid)
    transcript = []
    source = "none"
    srt = (a.get("closed_caption_urls") or {}).get("srt")
    if srt:
        try:
            r = requests.get(srt + ("" if "api_key=" in srt else f"&api_key={os.environ['DVIDS_API_KEY']}"), timeout=60)
            if r.ok and "-->" in r.text:
                transcript = srt_to_segments(r.text)
                source = "dvids_captions"
        except requests.RequestException:
            pass
    if not transcript:
        transcript = transcribe(vid)
        source = "whisper"
    sid = safe_id(asset_id)
    start = float(a.get("time_start") or 0)
    times = frame_sheet(vid, CANDIDATES / f"{sid}.jpg", duration, start=start)
    loc = a.get("location") or {}
    cand = {
        "id": sid,
        "asset_id": asset_id,
        "status": "new",
        "lane": lane,
        "matched_query": query,
        "harvested_at": iso(),
        "title": a.get("title"),
        "description": a.get("description"),
        "keywords": a.get("keywords"),
        "date": a.get("date"),
        "date_published": a.get("date_published"),
        "branch": a.get("branch"),
        "unit_name": a.get("unit_name"),
        "credit": credit_text(a.get("credit")),
        "category": a.get("category"),
        "virin": a.get("virin"),
        "location": {k: loc.get(k) for k in ["city", "state", "country", "state_abbreviation", "country_abbreviation"]},
        "page_url": a.get("url"),
        "duration": round(duration, 2),
        "time_start": start,
        "source_file": {k: best.get(k) for k in ["src", "width", "height", "bitrate", "size"]},
        "aspect_ratio": a.get("aspect_ratio"),
        "transcript_source": source,
        "transcript": transcript,
        "scene_cuts": scene_cuts(vid),
        "audio": loud_spans(vid),
        "sheet": f"data/candidates/{sid}.jpg",
        "sheet_times": times,
    }
    save_json(CANDIDATES / f"{sid}.json", cand)
    for f in work.glob("*"):
        f.unlink()
    return cand, None


def prune(days=45):
    """Drop frame sheets of old candidates nobody used, to keep the repo small."""
    cutoff = now_utc() - timedelta(days=days)
    for j in CANDIDATES.glob("*.json"):
        c = load_json(j)
        if c.get("status") in ("new", "passed_over") and c.get("harvested_at", "") < iso(cutoff):
            img = CANDIDATES / f"{c['id']}.jpg"
            if img.exists():
                img.unlink()
            c["status"] = "expired"
            save_json(j, c)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cfg = config()["harvest"]
    seen = load_json(SEEN, {})
    first = not seen
    days = cfg["first_run_backfill_days"] if first else cfg["lookback_days"]
    since = iso(now_utc() - timedelta(days=days))
    limit = args.limit or cfg["max_new_per_run"]

    found = {}
    for q in cfg["queries"]:
        try:
            results = search(q, since, cfg)
        except Exception as e:  # keep going on one bad query
            print(f"query {q['q']!r} failed: {e}")
            continue
        for r in results:
            aid = r.get("id")
            if aid and aid not in seen and aid not in found:
                found[aid] = (q["lane"], q["q"], r.get("title"))
        print(f"{q['q']!r}: {len(results)} results, {len(found)} new so far")
    print(f"{len(found)} unseen assets; processing up to {limit}")
    if args.dry_run:
        for aid, (lane, q, title) in list(found.items())[:limit]:
            print(lane, aid, title)
        return

    done = 0
    for aid, (lane, q, title) in found.items():
        if done >= limit:
            break
        try:
            cand, why = process(aid, lane, q)
        except Exception as e:
            cand, why = None, f"error: {e}"[:300]
        seen[aid] = {"at": iso(), "result": "candidate" if cand else why}
        print(("OK   " if cand else "SKIP ") + f"{aid} {title!r} {why or ''}")
        if cand:
            done += 1
        save_json(SEEN, seen)
    prune()
    save_json(DATA / "harvest_last.json", {"at": iso(), "new_candidates": done, "unseen_found": len(found)})


if __name__ == "__main__":
    main()
