"""Upload QA-passed Shorts to YouTube as scheduled videos, then post the question comment.

Each run fills open publish slots inside the lead window, up to the daily target
in config/channel.json. Uploads are private with a publishAt time, so YouTube
makes them public on schedule. Does nothing while uploads_enabled is false.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, WORK, config, iso, load_json, now_utc, save_json, short_dirs, short_state  # noqa: E402
import yt  # noqa: E402

ALERTS = DATA / "alerts.json"


def alert(kind, msg):
    a = load_json(ALERTS, [])
    a.append({"at": iso(), "kind": kind, "message": msg[:500]})
    save_json(ALERTS, a[-100:])
    print(f"ALERT {kind}: {msg}")


def pick_slots(cfg, n):
    slots = cfg["publish_slots_local"]
    if n >= len(slots):
        return slots
    if n <= 1:
        return [slots[len(slots) // 2]]
    return [slots[round(i * (len(slots) - 1) / (n - 1))] for i in range(n)]


def scheduled_times():
    taken = set()
    per_day = {}
    for d in short_dirs():
        u = load_json(d / "upload.json")
        if u and u.get("publish_at"):
            taken.add(u["publish_at"])
            day = u.get("slot_day")
            if day:
                per_day[day] = per_day.get(day, 0) + 1
    return taken, per_day


def open_slots(cfg):
    tz = ZoneInfo(cfg["timezone"])
    now = now_utc()
    horizon = now + timedelta(hours=cfg["upload_lead_hours"])
    taken, per_day = scheduled_times()
    target = min(int(cfg["daily_target"]), int(cfg["max_daily"]))
    out = []
    local_today = now.astimezone(tz).date()
    for offset in range(0, 3):
        day = local_today + timedelta(days=offset)
        used = per_day.get(day.isoformat(), 0)
        for hhmm in pick_slots(cfg, target):
            if used >= target:
                break
            h, m = map(int, hhmm.split(":"))
            local = datetime(day.year, day.month, day.day, h, m, tzinfo=tz)
            utc = local.astimezone(ZoneInfo("UTC"))
            stamp = utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            if utc < now + timedelta(minutes=25) or utc > horizon or stamp in taken:
                continue
            out.append((stamp, day.isoformat()))
            used += 1
    return out


def ready_shorts():
    rows = []
    for d in short_dirs():
        if short_state(d) == "passed":
            qa = load_json(d / "qa.json") or {}
            spec = load_json(d / "spec.json")
            rows.append((spec.get("priority", 5), qa.get("at", ""), d))
    rows.sort(key=lambda r: (r[0], r[1]))
    return [r[2] for r in rows]


def download_render(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return dest


def upload_video(path, spec, publish_at, cfg):
    meta = {
        "snippet": {
            "title": spec["title"],
            "description": spec["description"],
            "tags": spec["tags"],
            "categoryId": cfg["category_id"],
            "defaultLanguage": cfg["default_language"],
            "defaultAudioLanguage": cfg["default_language"],
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_at,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": bool(cfg.get("contains_synthetic_media", False)),
            "embeddable": True,
        },
    }
    size = path.stat().st_size
    init = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos",
        params={"uploadType": "resumable", "part": "snippet,status"},
        headers={**yt.headers(), "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)},
        data=json.dumps(meta), timeout=60)
    if init.status_code >= 400:
        raise UploadError(init.status_code, init.text)
    loc = init.headers["Location"]
    with open(path, "rb") as f:
        r = requests.put(loc, data=f, headers={**yt.headers(), "Content-Type": "video/mp4",
                                               "Content-Length": str(size)}, timeout=1800)
    if r.status_code >= 400:
        raise UploadError(r.status_code, r.text)
    return r.json()


class UploadError(Exception):
    def __init__(self, status, text):
        super().__init__(f"{status}: {text[:400]}")
        self.status = status
        self.text = text

    @property
    def reason(self):
        try:
            return json.loads(self.text)["error"]["errors"][0]["reason"]
        except Exception:
            return ""


def post_comments(limit=20):
    now = iso()
    done = 0
    for d in short_dirs():
        u = load_json(d / "upload.json")
        if not u or u.get("comment_id") or not u.get("video_id") or u.get("publish_at", "9") > now:
            continue
        spec = load_json(d / "spec.json")
        try:
            r = yt.api("POST", "/commentThreads", params={"part": "snippet"}, json={
                "snippet": {"videoId": u["video_id"],
                            "topLevelComment": {"snippet": {"textOriginal": spec["question_comment"]}}}})
            u["comment_id"] = r.get("id")
            u["commented_at"] = iso()
        except Exception as e:
            u["comment_error"] = str(e)[:300]
        save_json(d / "upload.json", u)
        done += 1
        if done >= limit:
            break
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cfg = config()
    commented = post_comments()
    if not cfg.get("uploads_enabled"):
        print("uploads_enabled is false; scheduling nothing")
        return
    lim = load_json(DATA / "upload_limit.json")
    if lim and lim.get("until", "") > iso():
        print(f"waiting out upload limit until {lim['until']}")
        return
    slots = open_slots(cfg)
    queue = ready_shorts()
    print(f"{len(slots)} open slots, {len(queue)} passed Shorts waiting, {commented} comments posted")
    n = 0
    for (stamp, day), d in zip(slots, queue):
        if n >= cfg["max_uploads_per_run"]:
            break
        spec = load_json(d / "spec.json")
        build = load_json(d / "build.json")
        if args.dry_run:
            print(f"would upload {d.name} for {stamp}")
            continue
        try:
            path = download_render(build["asset_url"], WORK / "up" / f"{d.name}.mp4")
            res = upload_video(path, spec, stamp, cfg)
        except UploadError as e:
            if e.reason in ("uploadLimitExceeded", "quotaExceeded", "rateLimitExceeded"):
                save_json(DATA / "upload_limit.json", {"at": iso(), "reason": e.reason, "uploaded_this_run": n,
                                                       "until": iso(now_utc() + timedelta(hours=12))})
                alert("upload_limit", f"YouTube said {e.reason} after {n} uploads this run")
                break
            if e.status in (401, 403):
                alert("auth", f"Upload sign-in problem: {e}")
                break
            alert("upload_error", f"{d.name}: {e}")
            continue
        except Exception as e:
            alert("upload_error", f"{d.name}: {e}")
            continue
        vid = res["id"]
        save_json(d / "upload.json", {"short_id": d.name, "video_id": vid, "url": f"https://youtube.com/shorts/{vid}",
                                      "publish_at": stamp, "slot_day": day, "uploaded_at": iso(),
                                      "title": spec["title"], "revision": spec.get("revision", 1)})
        print(f"uploaded {d.name} -> {vid} publishing {stamp}")
        n += 1
        path.unlink(missing_ok=True)
    save_json(DATA / "upload_last.json", {"at": iso(), "uploaded": n, "open_slots": len(slots),
                                          "waiting": len(queue)})


if __name__ == "__main__":
    main()
