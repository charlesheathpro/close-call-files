"""Make the extra copy of each double-uploaded Short private (never deletes anything).

Reads data/duplicates.json (written by upload.py --report-duplicates), keeps the copy with the most views
public, sets the others to private, and points the Short's upload.json at the copy that stays.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, iso, load_json, save_json, short_dirs  # noqa: E402
import yt  # noqa: E402
from upload import norm_title  # noqa: E402


def main():
    dupes = (load_json(DATA / "duplicates.json") or {}).get("duplicates", {})
    ids = [v for vs in dupes.values() for v in vs]
    if not ids:
        print("no duplicates")
        return
    info = {}
    for i in range(0, len(ids), 50):
        j = yt.api("GET", "/videos", params={"part": "statistics,status", "id": ",".join(ids[i:i + 50])})
        for it in j.get("items", []):
            info[it["id"]] = it
    by_title = {norm_title((load_json(d / "spec.json") or {}).get("title")): d for d in short_dirs()}
    log = []
    for title, vids in dupes.items():
        vids = [v for v in vids if v in info]
        keep = max(vids, key=lambda v: int(info[v]["statistics"].get("viewCount", 0)))
        for v in vids:
            if v == keep:
                continue
            st = dict(info[v]["status"])
            body = {"id": v, "status": {"privacyStatus": "private", "embeddable": st.get("embeddable", True),
                                        "selfDeclaredMadeForKids": False,
                                        "license": st.get("license", "youtube"),
                                        "publicStatsViewable": st.get("publicStatsViewable", True)}}
            yt.api("PUT", "/videos", params={"part": "status"}, json=body)
            log.append({"title": title, "made_private": v, "views": int(info[v]["statistics"].get("viewCount", 0)),
                        "kept": keep, "kept_views": int(info[keep]["statistics"].get("viewCount", 0))})
            print(f"{title}: kept {keep}, made {v} private")
        d = by_title.get(title)
        if d:
            u = load_json(d / "upload.json") or {}
            if u.get("video_id") != keep:
                u.update(video_id=keep, url=f"https://youtube.com/shorts/{keep}", repointed_at=iso())
                u.pop("comment_id", None)
                save_json(d / "upload.json", u)
    save_json(DATA / "duplicates_fixed.json", {"at": iso(), "fixed": log})
    print(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
