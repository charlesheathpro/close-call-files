"""Confirm every secret works. Writes data/secrets_check.json (no secret values)."""
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, iso, save_json  # noqa: E402
import yt  # noqa: E402

out = {"at": iso(), "checks": {}}
for name in ["DVIDS_API_KEY", "YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"]:
    out["checks"][f"{name} present"] = bool(os.environ.get(name))

try:
    r = requests.get("https://api.dvidshub.net/search", params={
        "api_key": os.environ.get("DVIDS_API_KEY", ""), "type[]": "video", "q": "rescue", "max_results": 1}, timeout=30)
    out["checks"]["dvids search"] = f"HTTP {r.status_code}"
except Exception as e:
    out["checks"]["dvids search"] = f"error {e}"

try:
    ch = yt.my_channel()
    out["checks"]["youtube sign-in"] = "ok"
    out["channel"] = {"id": ch["id"], "title": ch["snippet"]["title"], "handle": ch["snippet"].get("customUrl")} if ch else None
except Exception as e:
    out["checks"]["youtube sign-in"] = f"error {str(e)[:200]}"

try:
    j = yt.api("GET", "/reports", base="https://youtubeanalytics.googleapis.com/v2", params={
        "ids": "channel==MINE", "startDate": "2026-01-01", "endDate": iso()[:10], "metrics": "views"})
    out["checks"]["youtube analytics"] = "ok"
except Exception as e:
    out["checks"]["youtube analytics"] = f"error {str(e)[:200]}"

out["all_ok"] = all(v is True or v in ("ok", "HTTP 200") for v in out["checks"].values())
save_json(DATA / "secrets_check.json", out)
print(out)
