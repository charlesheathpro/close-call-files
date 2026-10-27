"""YouTube API helpers: access tokens from the stored refresh token."""
import os
import time

import requests

_token = {"value": None, "exp": 0}


def access_token():
    if _token["value"] and time.time() < _token["exp"] - 120:
        return _token["value"]
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["YT_CLIENT_ID"],
        "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"YouTube sign-in refresh failed: {r.status_code} {r.text[:300]}")
    j = r.json()
    _token.update(value=j["access_token"], exp=time.time() + int(j.get("expires_in", 3600)))
    return _token["value"]


def headers():
    return {"Authorization": "Bearer " + access_token()}


def api(method, path, base="https://www.googleapis.com/youtube/v3", **kw):
    r = requests.request(method, base + path, headers=headers(), timeout=kw.pop("timeout", 60), **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"YouTube API {method} {path} -> {r.status_code}: {r.text[:500]}")
    return r.json() if r.text else {}


def my_channel():
    j = api("GET", "/channels", params={"part": "snippet,statistics", "mine": "true"})
    items = j.get("items") or []
    return items[0] if items else None
