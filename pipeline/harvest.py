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
from common import (CANDIDATES, DATA, FONTS, WORK, config, copyright_flags, ffprobe, iso, load_json,  # noqa: E402
                    media_duration, now_utc, run, safe_id, save_json)
import sources  # noqa: E402

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


def search(query, since, cfg, max_pages=1):
    out = []
    for page in range(1, max_pages + 1):
        res = search_page(query, since, cfg, page)
        out.extend(res)
        if len(res) < 50:
            break
    return out


def search_page(query, since, cfg, page):
    params = {
        "page": page,
        "type[]": "video",
        "q": query["q"],
        **({"from_publishdate": since} if since else {"sort": "score"}),
        "from_duration": cfg["min_duration"],
        "to_duration": cfg["max_duration"],
        **({"sort": "publishdate", "sortdir": "desc"} if since else {}),
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
    with requests.get(url, stream=True, timeout=120, headers=sources.UA) as r:
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
    probe = run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0",
                 str(video)], check=False)
    if not (probe.stdout or "").strip():
        return []
    import numpy as np
    raw = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
               "-f", "s16le", "-"], capture=True, check=False, binary=True).stdout
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if audio.size < 16000:
        return []
    segments, _ = _whisper.transcribe(audio, vad_filter=True, beam_size=1)
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


def drama_score(video, duration):
    """0-100: how much the picture moves and changes. Static, calm footage scores low."""
    import numpy as np
    raw = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video), "-vf",
               "fps=2,scale=64:36,format=gray", "-f", "rawvideo", "-"], check=False, binary=True).stdout
    frames = np.frombuffer(raw, dtype=np.uint8)
    if frames.size < 64 * 36 * 4:
        return 0
    frames = frames[: frames.size // (64 * 36) * 64 * 36].reshape(-1, 36, 64).astype(np.float32)
    diffs = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))
    motion = float(np.percentile(diffs, 75))
    contrast = float(frames.std(axis=(1, 2)).mean())
    return int(min(100, motion * 6 + contrast * 0.6))


def dark_share(video):
    """Share of sampled frames that are mostly black: night hoists and thermal windows."""
    import numpy as np
    raw = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video), "-vf",
               "fps=1,scale=64:36,format=gray", "-f", "rawvideo", "-"], check=False, binary=True).stdout
    frames = np.frombuffer(raw, dtype=np.uint8)
    if frames.size < 64 * 36:
        return 0.0
    frames = frames[: frames.size // (64 * 36) * 64 * 36].reshape(-1, 36 * 64)
    live = frames.max(axis=0) >= 40  # ignore letterbox and pillarbox bars that are black in every frame
    if live.sum() < 50:
        return 1.0
    return float(((frames[:, live] < 40).mean(axis=1) > 0.6).mean())


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


ROUTINE = re.compile(r"\b(training|exercise|drill|ceremony|change of command|award|memorial|interview|press conference|"
                     r"briefing|graduation|retirement|visit|tour|promotion|reenlistment|recruit|band|concert|"
                     r"psa|highlights|b-roll package|safety tips|demonstration|demo|lava dogs?|live fire|range \d+|muster|clears?|clean ?up|repairs?|route clearance|debris|monitors?|prepares?|preparation|standby|funding|greets?|invictus|army.navy|noble jump|trident juncture|redeploy\w*|homecoming|satellites?|from space|explainer|profile|spotlight|highlight reel|recap)\b", re.I)
HOOKS = [(r"\b(infant|baby|child|children|boy|girl|toddler|teen)", 5), (r"\b(dog|dogs|cat|puppy|pet|horse)\b", 5),
         (r"\b(family|mother|father|elderly|grandmother)\b", 4), (r"rooftop|roof\b", 4),
         (r"\b(surf|waves|heavy seas|storm)\b", 3), (r"\b(fire|burning|explosion)\b", 3),
         (r"\b(sinking|sank|capsiz|overturn|rollover)", 3), (r"\b(cliff|ice|stranded|trapped|clinging)\b", 3),
         (r"\b(hurricane|flood)", 2), (r"\b(rescue|rescues|hoist|saves|saved)\b", 2),
         (r"\b(ejection|ejects|crash|arrest|barricade)", 3),
         (r"\b(lava|eruption|erupt|volcan|tornado|wildfire|avalanche|landslide|mudslide|tsunami|waterspout|lightning)", 3),
         (r"\b(abort|anomaly|failure|explod|impact|splashdown|eye of|hurricane hunter|whiteout|blizzard)", 3)]


def title_score(title):
    t = title or ""
    if ROUTINE.search(t):
        return -1
    return sum(w for rx, w in HOOKS if re.search(rx, t, re.I))


def analyze(sid, meta, best_src, small_src, best_info=None, srt_text=None):
    """Download the small file once, transcribe, cut scenes, score drama and save the candidate."""
    work = WORK / sid
    work.mkdir(parents=True, exist_ok=True)
    if best_info is not None and not (best_info.get("width") and best_info.get("height")):
        probed = sources.probe_url(best_src)
        if probed:
            best_info.update(width=probed["width"], height=probed["height"])
    if best_info and best_info.get("width") and best_info.get("height"):
        short = min(int(best_info["width"]), int(best_info["height"]))
        if short < config()["harvest"].get("min_short_side", 700):
            return None, f"low resolution ({best_info['width']}x{best_info['height']})"
    vid = download(small_src, work / "analysis.mp4")
    duration = media_duration(vid)
    dark = dark_share(vid)
    if dark > 0.6:
        for f in work.glob("*"):
            f.unlink()
        return None, f"mostly dark ({dark:.0%} of frames)"
    transcript, source = [], "none"
    if srt_text and "-->" in srt_text:
        transcript, source = srt_to_segments(srt_text), "captions"
    if not transcript:
        transcript, source = transcribe(vid), "whisper"
    start = float(meta.get("time_start") or 0)
    times = frame_sheet(vid, CANDIDATES / f"{sid}.jpg", duration, start=start)
    if not best_info:
        v = next((st for st in ffprobe(vid)["streams"] if st["codec_type"] == "video"), {})
        best_info = {"src": best_src, "width": v.get("width"), "height": v.get("height")}
    cand = dict(meta)
    cand.update({
        "id": sid, "status": "new", "harvested_at": iso(), "duration": round(duration, 2), "time_start": start,
        "source_file": best_info, "transcript_source": source, "transcript": transcript,
        "scene_cuts": scene_cuts(vid), "drama_score": drama_score(vid, duration), "audio": loud_spans(vid),
        "sheet": f"data/candidates/{sid}.jpg", "sheet_times": times,
    })
    save_json(CANDIDATES / f"{sid}.json", cand)
    for f in work.glob("*"):
        f.unlink()
    return cand, None


def process(asset_id, lane, query):
    if asset_id.startswith("nasa:"):
        return sources.process_nasa(asset_id, lane, query, analyze)
    if asset_id.startswith("commons:"):
        return sources.process_commons(asset_id, lane, query, analyze)
    a = asset(asset_id)
    if not a:
        return None, "asset lookup empty"
    flags = copyright_flags(a.get("title"), a.get("description"), a.get("keywords"))
    if flags:
        return None, "copyright flags: " + ", ".join(flags)
    best, small = pick_files(a.get("files"))
    if not best:
        return None, "no mp4 files"
    srt_text = None
    srt = (a.get("closed_caption_urls") or {}).get("srt")
    if srt:
        try:
            r = requests.get(srt + ("" if "api_key=" in srt else f"&api_key={os.environ['DVIDS_API_KEY']}"), timeout=60)
            srt_text = r.text if r.ok else None
        except requests.RequestException:
            pass
    loc = a.get("location") or {}
    meta = {
        "asset_id": asset_id, "source": "dvids", "lane": lane, "matched_query": query,
        "title": a.get("title"), "description": a.get("description"), "keywords": a.get("keywords"),
        "date": a.get("date"), "date_published": a.get("date_published"), "branch": a.get("branch"),
        "unit_name": a.get("unit_name"), "credit": credit_text(a.get("credit")), "category": a.get("category"),
        "virin": a.get("virin"),
        "location": {k: loc.get(k) for k in ["city", "state", "country", "state_abbreviation", "country_abbreviation"]},
        "page_url": a.get("url"), "via": "DVIDS", "license": "Public domain (U.S. government work)",
        "time_start": float(a.get("time_start") or 0), "aspect_ratio": a.get("aspect_ratio"),
    }
    return analyze(safe_id(asset_id), meta, best["src"], small["src"],
                   {k: best.get(k) for k in ["src", "width", "height", "bitrate", "size"]}, srt_text)


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
    ap.add_argument("--archive", action="store_true", help="run the high-drama searches across all years")
    args = ap.parse_args()
    cfg = config()["harvest"]
    seen = load_json(SEEN, {})
    first = not seen
    days = cfg["first_run_backfill_days"] if first else cfg["lookback_days"]
    since = iso(now_utc() - timedelta(days=days))
    limit = args.limit or cfg["max_new_per_run"]

    found = {}
    queries = [(q, since, cfg["backfill_pages"] if first else cfg["daily_pages"]) for q in cfg["queries"]]
    if args.archive or first:
        queries = [(q, None, cfg.get("drama_pages", 2)) for q in cfg.get("drama_queries", [])] + queries
    else:  # every daily run also takes one page from two rotating drama searches
        dq = cfg.get("drama_queries", [])
        day = int(now_utc().strftime("%j"))
        n = min(cfg.get("daily_drama_queries", 12), len(dq))
        queries = [(dq[(day * n + k) % len(dq)], None, 2) for k in range(n)] + queries
    for q, q_since, pages in queries:
        try:
            results = search(q, q_since, cfg, max_pages=pages)
        except Exception as e:  # keep going on one bad query
            print(f"query {q['q']!r} failed: {e}")
            continue
        for r in results:
            aid = r.get("id")
            if aid and aid not in seen and aid not in found:
                found[aid] = (q["lane"], q["q"], r.get("title"))
        print(f"{q['q']!r}: {len(results)} results, {len(found)} new so far")
    # NASA and U.S. federal works on Wikimedia Commons
    day = int(now_utc().strftime("%j"))
    n_o = cfg.get("daily_other_queries", 4)
    for src_name, fn in (("nasa", sources.search_nasa), ("commons", sources.search_commons)):
        qs = cfg.get(f"{src_name}_queries", [])
        if not qs:
            continue
        pick = qs if (args.archive or first) else [qs[(day * n_o + k) % len(qs)] for k in range(min(n_o, len(qs)))]
        for q in pick:
            try:
                for aid, title in fn(q["q"]):
                    if aid not in seen and aid not in found:
                        found[aid] = (q["lane"], q["q"], title)
            except Exception as e:
                print(f"{src_name} query {q['q']!r} failed: {e}")
        print(f"after {src_name}: {len(found)} new so far")
    # drop routine footage by title, then strongest stories first
    for aid in [a for a, v in found.items() if title_score(v[2]) < 0]:
        seen[aid] = {"at": iso(), "result": "routine title"}
        found.pop(aid)
    found = dict(sorted(found.items(), key=lambda kv: -title_score(kv[1][2])))
    # interleave lanes and sources so each gets a share of the run
    by_lane = {}
    for aid, v in found.items():
        src = aid.split(":", 1)[0] if aid.startswith(("nasa:", "commons:")) else "dvids"
        by_lane.setdefault((v[0], src), []).append((aid, v))
    # weighted by lane_mix: rescue performs best, so it gets the biggest share of each run
    mix = config().get("lane_mix", {})
    credit = {k: 0.0 for k in by_lane}
    mixed = []
    while any(by_lane.values()):
        live = [k for k in by_lane if by_lane[k]]
        for k in live:
            credit[k] += max(mix.get(k[0], 0.1), 0.05) / max(sum(1 for j in live if j[0] == k[0]), 1)
        k = max(live, key=lambda j: credit[j])
        credit[k] -= 1
        mixed.append(by_lane[k].pop(0))
    found = dict(mixed)
    print(f"{len(found)} unseen assets; processing up to {limit}")
    if args.dry_run:
        for aid, (lane, q, title) in list(found.items())[:limit]:
            print(lane, aid, title)
        return

    done = errors = streak = 0
    t0, budget = time.time(), float(os.environ.get("HARVEST_MINUTES", 0)) * 60
    for aid, (lane, q, title) in found.items():
        if done >= limit:
            break
        if budget and time.time() - t0 > budget:
            print("time budget used up; the rest waits for the next run")
            break
        try:
            cand, why = process(aid, lane, q)
            streak = 0
        except Exception as e:
            errors += 1
            streak += 1
            print(f"ERROR {aid} {title!r}: {e}"[:400])
            if streak >= 5:
                print("5 errors in a row; stopping so nothing gets wrongly marked as seen")
                break
            continue  # errors are retried next run, never marked seen
        seen[aid] = {"at": iso(), "result": "candidate" if cand else why}
        print(("OK   " if cand else "SKIP ") + f"{aid} {title!r} {why or ''}")
        if cand:
            done += 1
        save_json(SEEN, seen)
    prune()
    save_json(DATA / "harvest_last.json", {"at": iso(), "new_candidates": done, "errors": errors, "unseen_found": len(found)})


if __name__ == "__main__":
    main()
