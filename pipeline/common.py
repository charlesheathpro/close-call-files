"""Shared helpers for the Close Call Files pipeline."""
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "channel.json"
DATA = ROOT / "data"
CANDIDATES = DATA / "candidates"
SHORTS = DATA / "shorts"
STATS = DATA / "stats"
FONTS = ROOT / "assets" / "fonts"
WORK = Path(os.environ.get("CCF_WORK", "/tmp/ccf"))

ORANGE = "#FF5A1F"
INK = "#111418"


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt=None):
    return (dt or now_utc()).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    with open(path) as f:
        return json.load(f)


def save_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)


def config():
    return load_json(CONFIG)


def run(cmd, check=True, capture=True, binary=False):
    """Run a command list; return CompletedProcess."""
    res = subprocess.run([str(c) for c in cmd], text=not binary, capture_output=capture)
    if check and res.returncode != 0:
        err = res.stderr.decode(errors="replace") if binary and res.stderr else (res.stderr or "")
        raise RuntimeError(f"command failed ({res.returncode}): {' '.join(map(str, cmd))[:400]}\n{err[-2000:]}")
    return res


def ffprobe(path):
    res = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    return json.loads(res.stdout)


def media_duration(path):
    return float(ffprobe(path)["format"]["duration"])


def safe_id(asset_id):
    """'video:123456' -> 'dvids-video-123456'."""
    return "dvids-" + re.sub(r"[^a-zA-Z0-9]+", "-", asset_id).strip("-")


# Phrases that signal footage is NOT a plain U.S. government work.
COPYRIGHT_FLAGS = [
    r"copyright", r"©", r"all rights reserved", r"used with permission",
    r"not for (?:commercial|resale)", r"licensed (?:from|by)", r"getty", r"associated press", r"\breuters\b",
    r"news station", r"\bwfaa\b", r"\bkhou\b", r"\bfox ?\d", r"\bnbc\b", r"\bcbs\b", r"\babc news\b", r"\bcnn\b",
    r"cell ?phone footage", r"civilian footage", r"provided by (?!(?:the )?u\.?s\.?)",
]
_COPYRIGHT_RE = re.compile("|".join(COPYRIGHT_FLAGS), re.IGNORECASE)


FEDERAL_WORDS = re.compile(
    r"u\.?\s?s\.?\b|united states|coast guard|uscg|navy|naval|army|air force|marine|space force|national guard|"
    r"air station|sector|district|cutter|uss\b|uscgc|squadron|wing\b|battalion|regiment|brigade|command|fleet|"
    r"base\b|public affairs|department of|dod\b|dvids|nasa|noaa|usgs|fema|joint task force|station\b|division|"
    r"corps|group\b|detachment|airlift|carrier|strike group|task force", re.IGNORECASE)
_COURTESY_RE = re.compile(r"courtesy", re.IGNORECASE)
RANKS = re.compile(r"\b(?:pfc|pvt|spc|sgt|ssgt|cpl|lt|capt|maj|col|cmdr|cdr|lcdr|ens|ensign|seaman|airman|"
                   r"petty officer|chief|mc[1-3]|mcs[an]|senior airman|staff sgt|tech\. sgt|aircrew|crew|unit)\b",
                   re.IGNORECASE)


def copyright_flags(*texts):
    hits = set()
    for t in texts:
        if not t:
            continue
        for m in _COPYRIGHT_RE.finditer(t):
            hits.add(m.group(0).lower())
        # "courtesy of X" is fine when X is a federal unit, a red flag otherwise
        for m in _COURTESY_RE.finditer(t):
            # the parenthetical or sentence around the word decides
            a = max(t.rfind("(", 0, m.start()), t.rfind(". ", 0, m.start()), t.rfind("\n", 0, m.start()))
            ends = [i for i in (t.find(")", m.end()), t.find(". ", m.end()), t.find("\n", m.end())) if i != -1]
            b = min(ends) if ends else len(t)
            ctx = t[a + 1:b]
            if not (FEDERAL_WORDS.search(ctx) or RANKS.search(ctx)):
                hits.add("courtesy: " + ctx.strip().lower()[:60])
    return sorted(hits)


# Writing rules that apply to every word the channel publishes.
BANNED_PATTERNS = [
    (re.compile("—"), "em-dash"),
    (re.compile("–"), "en-dash used as a dash"),
    (re.compile(r"(?<!-)--(?!-)"), "double hyphen dash"),
    (re.compile(r"\bnot (?:just |only |simply |merely )?(?:a |an |the )?[\w' -]{1,40}?,? but\b", re.I), "'not X but Y' phrasing"),
    (re.compile(r"\bisn't (?:just |only )?[\w' -]{1,40}?,? (?:it's|it is)\b", re.I), "'isn't X, it's Y' phrasing"),
    (re.compile(r"\bwasn't (?:just |only )?[\w' -]{1,40}?,? (?:it was)\b", re.I), "'wasn't X, it was Y' phrasing"),
    (re.compile(r"\bmore than just\b", re.I), "'more than just' phrasing"),
]


def writing_problems(text):
    probs = []
    for rx, label in BANNED_PATTERNS:
        if rx.search(text or ""):
            probs.append(label)
    return probs


def short_dirs():
    if not SHORTS.exists():
        return []
    return sorted(p for p in SHORTS.iterdir() if p.is_dir())


def short_state(d):
    """Derive the status of one Short from the files its stages wrote."""
    d = Path(d)
    spec = load_json(d / "spec.json")
    build = load_json(d / "build.json")
    qa = load_json(d / "qa.json")
    up = load_json(d / "upload.json")
    if not spec:
        return "empty"
    if spec.get("status") == "dropped":
        return "dropped"
    if up and up.get("video_id"):
        return "uploaded"
    rev = spec.get("revision", 1)
    if not build or build.get("revision") != rev:
        return "needs_build"
    if build.get("status") != "ok":
        return "build_failed"
    if not qa or qa.get("revision") != rev:
        return "needs_qa"
    if qa.get("verdict") == "pass":
        return "passed"
    return "rejected"
