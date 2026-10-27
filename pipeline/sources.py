"""Footage sources beyond DVIDS.

NASA Image and Video Library: every item is a NASA work unless the
description credits someone else, which copyright_flags catches.

Wikimedia Commons: only files tagged as U.S. federal government works
(PD-USGov and its agency variants: NOAA, USGS, NPS, FEMA, Forest Service,
military branches). Anything else on Commons is skipped, because user
uploads with Creative Commons labels are too often reposts of someone
else's video.

Each search_* returns [(asset_id, title)]; each process_* returns the
same (candidate, why_skipped) pair as the DVIDS path, via analyze().
"""
import html
import json
import re
import time
from urllib.parse import quote

import requests

from common import config, copyright_flags, run

UA = {"User-Agent": "CloseCallFilesHarvester/1.0 (+https://charlessheath.com)"}


def _get(url, params=None, tries=4):
    for attempt in range(tries):
        r = requests.get(url, params=params, headers=UA, timeout=60)
        if r.status_code in (429, 503):
            time.sleep(8 * (attempt + 1))
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()


def _limits():
    h = config()["harvest"]
    return h.get("min_duration", 15), h.get("max_duration", 1200)


def probe_url(url):
    """Width, height and size of a remote video without downloading it."""
    res = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
               "-of", "json", "-user_agent", UA["User-Agent"], url], check=False)
    try:
        st = json.loads(res.stdout)["streams"][0]
        return {"src": url, "width": int(st["width"]), "height": int(st["height"])}
    except (ValueError, KeyError, IndexError):
        return None


def _clean(text):
    text = re.sub(r"<br\s*/?>", "\n", text or "")
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


# ---------------------------------------------------------------- NASA

NASA = "https://images-api.nasa.gov"


def search_nasa(q, pages=2):
    out = []
    for page in range(1, pages + 1):
        d = _get(f"{NASA}/search", {"q": q, "media_type": "video", "page": page}).json()["collection"]
        for it in d.get("items", []):
            meta = (it.get("data") or [{}])[0]
            if meta.get("nasa_id"):
                out.append(("nasa:" + meta["nasa_id"], meta.get("title") or ""))
        if not any(l.get("rel") == "next" for l in d.get("links", [])):
            break
    return out


def process_nasa(asset_id, lane, query, analyze):
    nid = asset_id.split(":", 1)[1]
    d = _get(f"{NASA}/search", {"nasa_id": nid}).json()["collection"]["items"]
    if not d:
        return None, "nasa item missing"
    meta = d[0]["data"][0]
    desc = meta.get("description") or meta.get("description_508") or ""
    who = " ".join(filter(None, [meta.get("photographer"), meta.get("secondary_creator")]))
    flags = copyright_flags(meta.get("title"), desc, who)
    if flags:
        return None, "copyright flags: " + ", ".join(flags)
    hrefs = [requests.utils.requote_uri(i["href"].replace("http://", "https://"))
             for i in _get(f"{NASA}/asset/{quote(nid)}").json()["collection"]["items"]]
    def pick(*names):
        for n in names:
            for h in hrefs:
                if h.endswith(f"~{n}.mp4"):
                    return h
    small = pick("small", "mobile", "medium", "large", "orig")
    best, best_info = None, None
    for name in ("orig", "large", "medium"):
        url = pick(name)
        if not url:
            continue
        info = probe_url(url)
        if info and min(info["width"], info["height"]) <= 1080:
            best, best_info = url, info
            break
    if not best:
        return None, "no usable mp4 files"
    srt = next((h for h in hrefs if h.endswith(".srt")), None)
    srt_text = None
    if srt:
        try:
            srt_text = _get(srt, tries=2).text
        except requests.RequestException:
            pass
    center = meta.get("center") or ""
    credit = "NASA" + (f" {center}" if center and center != "HQ" else "")
    page = f"https://images.nasa.gov/details/{quote(nid)}"
    m = {
        "asset_id": asset_id, "source": "nasa", "lane": lane, "matched_query": query,
        "title": meta.get("title"), "description": _clean(desc), "keywords": ", ".join(meta.get("keywords") or []),
        "date": meta.get("date_created"), "branch": "NASA", "unit_name": credit, "credit": credit + " video",
        "page_url": page, "via": "the NASA Image and Video Library",
        "license": "Public domain (NASA work, U.S. government)", "location": {}, "time_start": 0.0,
    }
    cand, why = analyze("nasa-" + re.sub(r"[^a-zA-Z0-9]+", "-", nid).strip("-")[:80], m, best, small, best_info, srt_text)
    if cand:
        lo, hi = _limits()
        if not lo <= cand["duration"] <= hi:
            return None, f"duration {cand['duration']:.0f}s outside limits"
    return cand, why


# ---------------------------------------------------------------- Wikimedia Commons

COMMONS = "https://commons.wikimedia.org/w/api.php"
# License templates that mean a U.S. federal government work.
FEDERAL_PD = re.compile(
    r"\bpd[- ]usgov\b|\bpd[- ]usgov[- ]\w+|"
    r"\bpd[- ]us[- ](?:gov|government|military|army|navy|air force|marine|coast guard|national guard|department|dhs|dod|"
    r"federal|cbp|customs|fema|fws|fish|forest|usda|nps|national park|noaa|nasa|usgs|faa|ntsb|doi|blm|army corps)|"
    r"\bpd[- ](?:nasa|noaa|usgs|nps|fema|usda|usfws|fws|nws)\b", re.IGNORECASE)
AGENCY = re.compile(
    r"noaa|usgs|national park service|\bnps\b|fema|forest service|nasa|coast guard|navy|army|air force|marine corps|"
    r"national guard|geological survey|weather service|fish and wildlife|bureau of land management|customs and border|faa|ntsb|department of", re.IGNORECASE)


def search_commons(q, limit=50):
    d = _get(COMMONS, {"action": "query", "list": "search", "srsearch": f"filetype:video {q}", "srnamespace": 6,
                       "srlimit": limit, "format": "json"}).json()
    return [("commons:" + r["title"], r["title"][5:].rsplit(".", 1)[0]) for r in d.get("query", {}).get("search", [])]


def process_commons(asset_id, lane, query, analyze):
    title = asset_id.split(":", 1)[1]
    d = _get(COMMONS, {"action": "query", "titles": title, "format": "json",
                       "prop": "imageinfo|videoinfo|categories", "cllimit": 50,
                       "iiprop": "url|size|extmetadata|mediatype",
                       "viprop": "derivatives"}).json()
    page = next(iter(d.get("query", {}).get("pages", {}).values()), {})
    info = (page.get("imageinfo") or [{}])[0]
    vinfo = (page.get("videoinfo") or [{}])[0]
    ext = info.get("extmetadata") or {}
    val = lambda k: _clean((ext.get(k) or {}).get("value"))  # noqa: E731
    lic = " ".join([val("License"), val("LicenseShortName"), val("UsageTerms"), val("Categories"),
                    " ".join(c.get("title", "") for c in page.get("categories", []))])
    if not FEDERAL_PD.search(lic):
        return None, "not a U.S. federal public domain work"
    artist, credit, desc = val("Artist"), val("Credit"), val("ImageDescription")
    flags = copyright_flags(desc, credit, artist)
    if flags:
        return None, "copyright flags: " + ", ".join(flags)
    dur = float(info.get("duration") or 0)
    lo, hi = _limits()
    if dur and not lo <= dur <= hi:
        return None, f"duration {dur:.0f}s outside limits"
    derivs = [x for x in vinfo.get("derivatives") or [] if x.get("src")]
    def h(x):
        return min(int(x.get("height") or 0), int(x.get("width") or 0))
    best_src = info.get("url")
    best_info = {"src": best_src, "width": info.get("width"), "height": info.get("height"), "size": info.get("size")}
    if h(info) > 1080 or (info.get("size") or 0) > 1.5e9:  # use the 1080p transcode for huge originals
        big = [x for x in derivs if 720 <= h(x) <= 1080]
        if big:
            b = max(big, key=h)
            best_src, best_info = b["src"], {"src": b["src"], "width": b.get("width"), "height": b.get("height")}
    small = [x for x in derivs if 300 <= h(x) <= 480]
    small_src = small[0]["src"] if small else best_src
    who = artist if AGENCY.search(artist or "") else (credit if AGENCY.search(credit or "") else (artist or credit or "U.S. government"))
    m = {
        "asset_id": asset_id, "source": "commons", "lane": lane, "matched_query": query,
        "title": title[5:].rsplit(".", 1)[0], "description": desc, "keywords": val("Categories").replace("|", ", "),
        "date": val("DateTimeOriginal") or val("DateTime"), "branch": "", "unit_name": who[:120],
        "credit": f"{who[:120]} video", "original_source": credit[:300],
        "page_url": info.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/{quote(title)}",
        "via": "Wikimedia Commons", "license": "Public domain (U.S. federal government work)",
        "location": {}, "time_start": 0.0,
    }
    sid = "commons-" + re.sub(r"[^a-zA-Z0-9]+", "-", m["title"]).strip("-")[:60]
    return analyze(sid, m, best_src, small_src, best_info, None)
