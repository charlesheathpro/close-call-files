"""Upload QA-passed Shorts to YouTube as scheduled videos, then post the question comment.

Each run fills open publish slots inside the lead window, up to the daily target
in config/channel.json. Uploads are private with a publishAt time, so YouTube
makes them public on schedule. Does nothing while uploads_enabled is false.
"""
import argparse
import json
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


def upload_times():
    out = []
    for d in short_dirs():
        u = load_json(d / "upload.json") or {}
        t = u.get("uploaded_at")
        if t:
            out.append(datetime.fromisoformat(t.replace("Z", "+00:00")))
    return out


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


def norm_title(t):
    return " ".join((t or "").lower().split())


def channel_titles(max_items=400):
    """Titles of every video already on the channel (scheduled and private included), read from YouTube itself.

    This is the guard against double uploads: whatever the repo says, a title YouTube already has is never sent again.
    Raises if YouTube cannot be read, so the run uploads nothing rather than risk a duplicate.
    """
    ch = yt.api("GET", "/channels", params={"part": "contentDetails", "mine": "true"})["items"][0]
    pl = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    out, token = {}, None
    while len(out) < max_items:
        params = {"part": "snippet,status", "playlistId": pl, "maxResults": 50}
        if token:
            params["pageToken"] = token
        j = yt.api("GET", "/playlistItems", params=params)
        for it in j.get("items", []):
            vid = it["snippet"]["resourceId"]["videoId"]
            out.setdefault(norm_title(it["snippet"]["title"]), []).append(vid)
        token = j.get("nextPageToken")
        if not token:
            break
    return out


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
    ap.add_argument("--quiet-if-idle", action="store_true", help="write no run record when nothing was uploaded")
    ap.add_argument("--report-duplicates", action="store_true", help="write data/duplicates.json and exit")
    args = ap.parse_args()
    if args.report_duplicates:
        dupes = {t: v for t, v in channel_titles().items() if len(v) > 1}
        save_json(DATA / "duplicates.json", {"at": iso(), "duplicates": dupes})
        print(json.dumps(dupes, indent=1))
        return
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
    on_youtube = channel_titles() if (slots and queue and not args.dry_run) else {}
    fresh = []
    for d in queue:
        spec = load_json(d / "spec.json")
        if norm_title(spec["title"]) in on_youtube:
            alert("duplicate_blocked", f"{d.name}: '{spec['title']}' is already on the channel "
                                       f"({', '.join(on_youtube[norm_title(spec['title'])])}); not uploading it again")
            save_json(d / "upload.json", {"short_id": d.name, "video_id": on_youtube[norm_title(spec["title"])][0],
                                          "recovered": True, "at": iso(), "title": spec["title"]})
            continue
        fresh.append(d)
    queue = fresh
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
                # the channel limit is a rolling 24 hours; the workflow's watch loop retries as soon as it reopens
                until = now_utc() + timedelta(hours=24 if e.reason == "quotaExceeded" else 1)
                if e.reason == "uploadLimitExceeded":
                    # the cap counts uploads in the last 24 h: room opens when the oldest of them turns 24 h old
                    recent = sorted(t for t in upload_times() if t > now_utc() - timedelta(hours=24))
                    if len(recent) >= 9:
                        until = max(recent[0] + timedelta(hours=24, minutes=2), now_utc() + timedelta(minutes=30))
                    else:
                        # YouTube's real cap is not always 10 per rolling day (it has refused after 5);
                        # when the count says there should be room, try again in 2 hours instead of idling a day
                        until = now_utc() + timedelta(hours=2)
                save_json(DATA / "upload_limit.json", {"at": iso(), "reason": e.reason, "uploaded_this_run": n,
                                                       "until": iso(until)})
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
        on_youtube.setdefault(norm_title(spec["title"]), []).append(vid)
        save_json(d / "upload.json", {"short_id": d.name, "video_id": vid, "url": f"https://youtube.com/shorts/{vid}",
                                      "publish_at": stamp, "slot_day": day, "uploaded_at": iso(),
                                      "title": spec["title"], "revision": spec.get("revision", 1)})
        print(f"uploaded {d.name} -> {vid} publishing {stamp}")
        n += 1
        path.unlink(missing_ok=True)
    if n or not args.quiet_if_idle:
        save_json(DATA / "upload_last.json", {"at": iso(), "uploaded": n, "open_slots": len(slots),
                                              "waiting": len(queue)})


if __name__ == "__main__":
    main()
