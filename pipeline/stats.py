"""Pull view and retention numbers for every uploaded Short.

Writes data/stats/latest.json (one row per Short with its lane and story type)
and a dated snapshot under data/stats/daily/. YouTube Analytics lags about two
days, so new Shorts show Data API views first and retention later.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import STATS, iso, load_json, save_json, short_dirs  # noqa: E402
import yt  # noqa: E402

ANALYTICS = "https://youtubeanalytics.googleapis.com/v2"


def chunks(xs, n):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def main():
    rows = {}
    for d in short_dirs():
        u = load_json(d / "upload.json")
        if not u or not u.get("video_id"):
            continue
        spec = load_json(d / "spec.json") or {}
        rows[u["video_id"]] = {
            "short_id": d.name, "video_id": u["video_id"], "url": u.get("url"), "title": u.get("title"),
            "publish_at": u.get("publish_at"), "lane": spec.get("lane"), "story_type": spec.get("story_type"),
            "hook": spec.get("hook"),
        }
    ids = list(rows)
    for group in chunks(ids, 50):
        j = yt.api("GET", "/videos", params={"part": "statistics,status", "id": ",".join(group)})
        for it in j.get("items", []):
            s = it.get("statistics", {})
            r = rows[it["id"]]
            r.update(views=int(s.get("viewCount", 0)), likes=int(s.get("likeCount", 0)),
                     comments=int(s.get("commentCount", 0)), privacy=it.get("status", {}).get("privacyStatus"),
                     upload_status=it.get("status", {}).get("uploadStatus"),
                     rejection=it.get("status", {}).get("rejectionReason"))
    if ids:
        start = min(r["publish_at"][:10] for r in rows.values() if r.get("publish_at"))
        for group in chunks(ids, 200):
            try:
                rep = yt.api("GET", "/reports", base=ANALYTICS, params={
                    "ids": "channel==MINE", "startDate": start, "endDate": iso()[:10], "dimensions": "video",
                    "metrics": "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
                               "likes,subscribersGained",
                    "filters": "video==" + ",".join(group), "maxResults": 200})
            except Exception as e:
                print(f"analytics error: {e}")
                continue
            cols = [c["name"] for c in rep.get("columnHeaders", [])]
            for row in rep.get("rows", []) or []:
                rec = dict(zip(cols, row))
                r = rows.get(rec.get("video"))
                if r:
                    r.update(a_views=rec.get("views"), avg_view_pct=rec.get("averageViewPercentage"),
                             avg_view_sec=rec.get("averageViewDuration"), minutes=rec.get("estimatedMinutesWatched"),
                             subs_gained=rec.get("subscribersGained"))
    ch = yt.my_channel()
    channel = {"subscribers": int(ch["statistics"].get("subscriberCount", 0)),
               "views": int(ch["statistics"].get("viewCount", 0)),
               "videos": int(ch["statistics"].get("videoCount", 0))} if ch else {}
    out = {"at": iso(), "channel": channel, "shorts": sorted(rows.values(), key=lambda r: r.get("publish_at") or "")}
    save_json(STATS / "latest.json", out)
    save_json(STATS / "daily" / f"{iso()[:10]}.json", out)
    print(f"{len(rows)} Shorts, channel {channel}")


if __name__ == "__main__":
    main()
