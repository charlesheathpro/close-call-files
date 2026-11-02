"""Nightly self-tuning: learn what works from the channel's own numbers and feed it back.

Runs after stats.py in the stats workflow, no Claude needed. It:
  1. scores every Short older than 48 hours (views, retention, subscribers per 1k views),
  2. measures which features go with better scores (lane, story type, hook with a child,
     an animal or a number, length, source, music mood, the harvest search that found it),
  3. writes data/review/playbook.json and playbook.md, which the editor reads before choosing clips,
  4. nudges config: lane_mix toward lanes that score better (at most 0.1 a day, never below 0.1),
     and search weights so the harvester digs deeper on searches whose Shorts did well,
  5. lists the last week's QA rejection notes so the editor stops repeating them.
"""
import json
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CANDIDATES, CONFIG, DATA, load_json, save_json, short_dirs  # noqa: E402

MATURE_H = 48
SHRINK = 3.0     # a feature needs a few Shorts before it moves anything
MIN_MATURE = 8   # below this, report only; change nothing

CHILD = re.compile(r"\b(child|children|kid|kids|baby|babies|toddler|boy|boys|girl|girls|teen|teens|\d+-year-old|"
                   r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)-year-old|son|sons|daughter)\b", re.I)
ANIMAL = re.compile(r"\b(dog|dogs|puppy|cat|cats|pet|pets|horse|horses|boxer)\b", re.I)
NUMBER = re.compile(r"\d|\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|"
                    r"hundred|thousand|mile|miles|feet|mph)\b", re.I)
FLOOD = re.compile(r"\b(flood|flooded|floodwater|hurricane|roof|rooftop)\b", re.I)
SPACE = re.compile(r"\b(rocket|booster|capsule|orion|starliner|artemis|nasa|abort|splash|parachute|chutes)\b", re.I)


def now():
    return datetime.now(timezone.utc)


def zscores(vals):
    m = sum(vals) / len(vals)
    sd = math.sqrt(sum((v - m) ** 2 for v in vals) / max(len(vals) - 1, 1)) or 1.0
    return [(v - m) / sd for v in vals]


def features(spec, cand, build):
    text = " ".join([spec.get("hook", ""), spec.get("title", ""), (spec.get("narration") or [""])[0]])
    dur = float((build or {}).get("duration") or 0)
    f = {
        f"lane: {spec.get('lane', '?')}": 1,
        f"source: {(cand or {}).get('source', 'dvids')}": 1,
        f"music: {spec.get('music_mood', 'none')}": 1,
        "hook names a child": bool(CHILD.search(text)),
        "hook names an animal": bool(ANIMAL.search(text)),
        "hook has a number": bool(NUMBER.search(text)),
        "flood or hurricane story": bool(FLOOD.search(text)),
        "spacecraft or test story": bool(SPACE.search(text)),
        "length under 30 s": 0 < dur < 30,
        "length 30 to 45 s": 30 <= dur < 45,
        "length 45 s or more": dur >= 45,
    }
    st = (spec.get("story_type") or "").lower().strip()
    if st:
        f[f"story: {st}"] = 1
    return {k for k, v in f.items() if v}


def main():
    stats = load_json(DATA / "stats" / "latest.json") or {}
    by_id = {s.get("short_id"): s for s in stats.get("shorts", []) if s.get("short_id")}
    rows = []
    for d in short_dirs():
        st = by_id.get(d.name)
        if not st or st.get("privacy") != "public" or not st.get("publish_at"):
            continue
        age_h = (now() - datetime.fromisoformat(st["publish_at"].replace("Z", "+00:00"))).total_seconds() / 3600
        if age_h < MATURE_H:
            continue
        spec = load_json(d / "spec.json") or {}
        cand = load_json(CANDIDATES / f"{spec.get('candidate_id')}.json") or {}
        build = load_json(d / "build.json") or {}
        views = float(st.get("views") or 0)
        rows.append({
            "short_id": d.name, "title": spec.get("title"), "views": views,
            "ret": float(st.get("avg_view_pct") or 0), "subs_k": 1000 * float(st.get("subs_gained") or 0) / max(views, 1),
            "query": cand.get("matched_query"), "lane": spec.get("lane"),
            "features": features(spec, cand, build),
        })
    out = {"at": now().strftime("%Y-%m-%dT%H:%M:%SZ"), "mature": len(rows)}
    if len(rows) >= 3:
        zv = zscores([math.log1p(r["views"]) for r in rows])
        zr = zscores([r["ret"] for r in rows])
        zs = zscores([r["subs_k"] for r in rows])
        for r, a, b, c in zip(rows, zv, zr, zs):
            r["score"] = round(0.5 * a + 0.35 * b + 0.15 * c, 3)
        allf = sorted({f for r in rows for f in r["features"]})
        feats = []
        for f in allf:
            inn = [r["score"] for r in rows if f in r["features"]]
            out_ = [r["score"] for r in rows if f not in r["features"]]
            if not inn or not out_:
                continue
            diff = sum(inn) / len(inn) - sum(out_) / len(out_)
            effect = diff * len(inn) / (len(inn) + SHRINK)
            feats.append({"feature": f, "n": len(inn), "effect": round(effect, 2)})
        feats.sort(key=lambda x: -x["effect"])
        out["features"] = feats
        ranked = sorted(rows, key=lambda r: -r["score"])
        pick = lambda r: {k: r[k] for k in ("short_id", "title", "views", "ret", "score")}  # noqa: E731
        out["top"] = [pick(r) for r in ranked[:5]]
        out["bottom"] = [pick(r) for r in ranked[-5:]]
        # search weights: searches whose Shorts beat the channel average get more pages
        qs = {}
        for r in rows:
            if r["query"]:
                qs.setdefault(r["query"], []).append(r["score"])
        out["query_weights"] = {q: round(max(0.5, min(2.0, math.exp(0.6 * (sum(v) / len(v)) * len(v) / (len(v) + SHRINK)))), 2)
                                for q, v in qs.items()}
        # lanes
        lanes = {}
        for r in rows:
            lanes.setdefault(r["lane"], []).append(r["score"])
        out["lane_scores"] = {k: round(sum(v) / len(v) * len(v) / (len(v) + SHRINK), 2) for k, v in lanes.items()}

    # QA lessons from the last 7 days
    cutoff = (now() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    lessons = []
    for d in short_dirs():
        q = load_json(d / "qa.json") or {}
        if q.get("verdict") == "reject" and q.get("at", "") >= cutoff and q.get("notes"):
            lessons.append({"short_id": d.name, "notes": q["notes"][:300]})
    out["qa_rejections_7d"] = lessons[-15:]

    cfg = load_json(CONFIG)
    changed = []
    prev = load_json(DATA / "review" / "playbook.json") or {}
    last = prev.get("config_changed_at") or ""
    once_a_day = not last or last < (now() - timedelta(hours=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out["config_changed_at"] = last
    if once_a_day and out["mature"] >= MIN_MATURE and out.get("lane_scores"):
        mix = dict(cfg.get("lane_mix", {}))
        sc = out["lane_scores"]
        weights = {k: math.exp(sc.get(k, 0.0)) * mix.get(k, 0.2) for k in mix}
        tot = sum(weights.values()) or 1
        target = {k: w / tot for k, w in weights.items()}
        new = {}
        for k in mix:
            step = max(-0.1, min(0.1, target[k] - mix[k]))
            new[k] = max(0.1, mix[k] + step)
        tot = sum(new.values())
        new = {k: round(v / tot, 2) for k, v in new.items()}
        if any(abs(new[k] - mix[k]) >= 0.02 for k in mix):
            cfg["lane_mix"] = new
            changed.append(f"lane_mix {mix} -> {new}")
    if once_a_day and out.get("query_weights"):
        old = cfg["harvest"].get("query_weights", {})
        if old != out["query_weights"]:
            cfg["harvest"]["query_weights"] = out["query_weights"]
            changed.append(f"query weights for {len(out['query_weights'])} searches")
    if changed:
        save_json(CONFIG, cfg)
        out["config_changed_at"] = out["at"]
    out["changed"] = changed
    save_json(DATA / "review" / "playbook.json", out)
    write_md(out)
    print(json.dumps({"mature": out["mature"], "changed": changed}, indent=1))


def write_md(o):
    lines = [f"# Playbook (computed {o['at']} from {o['mature']} Shorts older than 48 hours)", "",
             "Written every night by pipeline/learn.py from the channel's own numbers. Positive effect means Shorts with that "
             "feature beat the channel average (score mixes views, average percent watched and subscribers per 1,000 views).", ""]
    if o.get("features"):
        good = [f for f in o["features"] if f["effect"] >= 0.15][:8]
        bad = [f for f in reversed(o["features"]) if f["effect"] <= -0.15][:8]
        lines += ["## Do more of"] + [f"- {f['feature']} (+{f['effect']}, {f['n']} Shorts)" for f in good] + [""]
        lines += ["## Do less of"] + [f"- {f['feature']} ({f['effect']}, {f['n']} Shorts)" for f in bad] + [""]
        lines += ["## Best Shorts"] + [f"- {r['title']}: {int(r['views'])} views, {r['ret']:.0f}% watched" for r in o["top"]] + [""]
        lines += ["## Weakest Shorts"] + [f"- {r['title']}: {int(r['views'])} views, {r['ret']:.0f}% watched" for r in o["bottom"]] + [""]
    else:
        lines += ["Not enough mature Shorts yet.", ""]
    if o.get("qa_rejections_7d"):
        lines += ["## QA rejections this week (do not repeat these)"] + [f"- {r['short_id']}: {r['notes']}" for r in o["qa_rejections_7d"]] + [""]
    if o.get("changed"):
        lines += ["## Changed tonight"] + [f"- {c}" for c in o["changed"]] + [""]
    (DATA / "review" / "playbook.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
