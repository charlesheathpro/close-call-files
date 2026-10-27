"""Write the Control Room data files under data/dashboard/.

The review task uploads each file to the Control Room dashboard as a new
version of its attached source.
"""
import collections
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CANDIDATES, DATA, STATS, config, iso, load_json, now_utc, save_json, short_dirs, short_state  # noqa: E402

OUT = DATA / "dashboard"
STATE_ORDER = ["needs_build", "build_failed", "needs_qa", "rejected", "passed", "uploaded", "dropped"]
STATE_LABEL = {"needs_build": "Waiting to build", "build_failed": "Build failed", "needs_qa": "Waiting for QA",
               "rejected": "Sent back by QA", "passed": "Ready to upload", "uploaded": "Uploaded", "dropped": "Dropped"}


def main():
    cfg = config()
    stats = load_json(STATS / "latest.json", {"shorts": [], "channel": {}})
    by_vid = {s["short_id"]: s for s in stats.get("shorts", [])}

    shorts, counts = [], collections.Counter()
    for d in short_dirs():
        if d.name.startswith("ccf-test"):
            continue
        st = short_state(d)
        counts[st] += 1
        spec = load_json(d / "spec.json") or {}
        up = load_json(d / "upload.json") or {}
        s = by_vid.get(d.name, {})
        shorts.append({
            "short_id": d.name, "title": spec.get("title"), "lane": spec.get("lane"),
            "story_type": spec.get("story_type"), "status": STATE_LABEL.get(st, st),
            "publish_at": up.get("publish_at"), "views": s.get("views"),
            "avg_view_pct": s.get("avg_view_pct"), "url": up.get("url"),
        })
    pipeline = [{"stage": STATE_LABEL[k], "count": counts.get(k, 0)} for k in STATE_ORDER]

    supply = collections.Counter()
    for j in CANDIDATES.glob("*.json"):
        c = load_json(j)
        if c.get("status") == "new":
            supply[c.get("lane", "other")] += 1
    supply_rows = [{"lane": k, "new_clips": supply.get(k, 0)} for k in ["rescue", "aviation_naval", "hazards"]]

    # Daily rollup from snapshots
    daily = []
    for f in sorted((STATS / "daily").glob("*.json"))[-60:]:
        snap = load_json(f)
        day = f.stem
        pub = sum(1 for s in snap.get("shorts", []) if (s.get("publish_at") or "")[:10] == day)
        daily.append({"date": day, "shorts_views": sum(s.get("views") or 0 for s in snap.get("shorts", [])),
                      "subscribers": (snap.get("channel") or {}).get("subscribers"), "published": pub})

    now = now_utc()
    health = []
    h = load_json(DATA / "harvest_last.json")
    health.append({"item": "Harvest", "status": "ok" if h and h["at"] > iso(now - timedelta(hours=30)) else "warn",
                   "detail": f"Last run {h['at'][:16].replace('T', ' ')} UTC, {h['new_candidates']} new clips"
                   if h else "Has not run yet"})
    u = load_json(DATA / "upload_last.json")
    health.append({"item": "Uploads", "status": "ok" if cfg.get("uploads_enabled") else "warn",
                   "detail": (f"On, {cfg['daily_target']} a day" if cfg.get("uploads_enabled")
                              else "Off until samples are approved")
                   + (f". Last run uploaded {u['uploaded']}" if u else "")})
    alerts = [a for a in load_json(DATA / "alerts.json", []) if a["at"] > iso(now - timedelta(days=2))]
    health.append({"item": "Alerts (48 h)", "status": "bad" if alerts else "ok",
                   "detail": alerts[-1]["message"] if alerts else "None"})
    ready = counts.get("passed", 0)
    target = cfg["daily_target"]
    health.append({"item": "Ready buffer", "status": "ok" if ready >= target else "warn",
                   "detail": f"{ready} Shorts ready, {target} needed per day"})
    health.append({"item": "Clip supply", "status": "ok" if sum(supply.values()) >= 2 * target else "warn",
                   "detail": f"{sum(supply.values())} unused clips"})

    ch = stats.get("channel") or {}
    summary = [{"metric": "subscribers", "value": ch.get("subscribers")},
               {"metric": "channel_views", "value": ch.get("views")},
               {"metric": "shorts_uploaded", "value": counts.get("uploaded", 0)},
               {"metric": "daily_target", "value": target},
               {"metric": "uploads_enabled", "value": 1 if cfg.get("uploads_enabled") else 0}]

    meta = {"generated_at": iso()}
    for name, rows in [("shorts", shorts), ("pipeline", pipeline), ("supply", supply_rows), ("daily", daily),
                       ("health", health), ("summary", summary)]:
        save_json(OUT / f"{name}.json", {"rows": rows, **meta})
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
