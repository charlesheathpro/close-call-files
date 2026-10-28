"""Validate a Short spec before it is committed or built.

Usage: python pipeline/validate_spec.py data/shorts/<short_id>/spec.json [...]
Exit code 1 if any spec has errors. The editor task runs this before pushing.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CANDIDATES, load_json, writing_problems  # noqa: E402

TAG_RE = re.compile(r"\[[^\]\n]{1,60}\]")


def plain(t):
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", t or "")).strip()


LANES = {"rescue", "aviation_naval", "hazards"}
WORDS_PER_SEC = 2.9  # Brian on v4 measured at 166 to 176 words a minute


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def validate(spec_path):
    errors, warnings = [], []
    spec = load_json(spec_path)
    if spec is None:
        return [f"cannot read {spec_path}"], []
    req = ["short_id", "revision", "candidate_id", "lane", "story_type", "hook", "narration", "outcome",
           "location_card", "title", "description", "tags", "question_comment", "facts"]
    if not spec.get("line_shots") and not spec.get("segments"):
        errors.append("missing line_shots (one list of shots per narration line, plus one for the outcome)")
    for k in req:
        if k not in spec or spec[k] in (None, "", []):
            errors.append(f"missing {k}")
    if errors:
        return errors, warnings
    if Path(spec_path).parent.name != spec["short_id"]:
        errors.append("folder name must equal short_id")
    if spec["lane"] not in LANES:
        errors.append(f"lane must be one of {sorted(LANES)}")
    cand = load_json(CANDIDATES / f"{spec['candidate_id']}.json")
    if not cand:
        errors.append(f"candidate {spec['candidate_id']} not found")
        return errors, warnings

    # Text limits
    if len(spec["hook"]) > 70:
        errors.append("hook over 70 characters")
    if not isinstance(spec["narration"], list) or not 2 <= len(spec["narration"]) <= 16:
        errors.append("narration must be a list of 2 to 9 lines")
    for i, line in enumerate(spec["narration"] + [spec["outcome"]]):
        if len(TAG_RE.findall(line)) > 3:
            errors.append(f"line {i + 1}: at most 3 audio tags per line")
        if re.search(r"\[[^\]]*$|^[^\[]*\]", line):
            errors.append(f"line {i + 1}: unbalanced [ ] in audio tags")
    for i, line in enumerate(spec["narration"]):
        if len(plain(line)) > 170:
            errors.append(f"narration line {i + 1} over 170 characters")
    if len(plain(spec["outcome"])) > 150:
        errors.append("outcome over 150 characters")
    if len(spec["title"]) > 95:
        errors.append("title over 95 characters")
    elif len(spec["title"]) > 45:
        warnings.append("titles under about 40 characters perform best on Shorts")
    if "#" in spec["title"]:
        warnings.append("hashtags belong in the description, not the title")
    if len(spec["description"]) > 4500:
        errors.append("description too long")
    if not 3 <= len(spec["tags"]) <= 15:
        errors.append("use 3 to 15 tags")
    lc = spec["location_card"]
    if not lc.get("place") or not lc.get("date"):
        errors.append("location_card needs place and date")

    # Writing rules on everything the audience sees or hears
    texts = {"hook": spec["hook"], "outcome": plain(spec["outcome"]), "title": spec["title"],
             "description": spec["description"], "question_comment": spec["question_comment"],
             "location": lc.get("place", "")}
    for i, l in enumerate(spec["narration"]):
        texts[f"narration[{i + 1}]"] = plain(l)
    for name, t in texts.items():
        for p in writing_problems(t):
            errors.append(f"{name}: {p}")

    # The outcome must be spoken last and must actually resolve
    if norm(plain(spec["narration"][-1])) == norm(plain(spec["outcome"])):
        errors.append("do not repeat the outcome as the last narration line; the build speaks the outcome itself")
    if re.search(r"\b(?:will|unclear|unknown|remains to be seen|stay tuned|part 2|to be continued)\b", plain(spec["outcome"]), re.I):
        errors.append("outcome must state how it ended, in past tense, with no cliffhanger")

    # Grounding: every fact quote must appear in the agency release or transcript
    extras = spec.get("extra_sources") or []
    for i, x in enumerate(extras):
        if not str(x.get("url", "")).startswith("https://") or len(x.get("excerpt", "")) < 20:
            errors.append(f"extra_sources[{i + 1}] needs an https url and the copied excerpt")
    source_text = norm(" ".join([cand.get("title") or "", cand.get("description") or "",
                                 " ".join(s["text"] for s in cand.get("transcript", [])),
                                 " ".join(x.get("excerpt", "") for x in extras)]))
    if len(spec["facts"]) < 2:
        errors.append("list at least 2 facts with source quotes")
    for i, f in enumerate(spec["facts"]):
        q = norm(f.get("source_quote"))
        if not q or len(q) < 8:
            errors.append(f"fact {i + 1}: source_quote too short")
        elif q not in source_text:
            errors.append(f"fact {i + 1}: source_quote not found word for word in the release or transcript")

    # Footage
    dur = cand.get("duration", 0)
    total = 0.0
    lines_all = spec["narration"] + [spec["outcome"]]
    if spec.get("line_shots"):
        ls = spec["line_shots"]
        if len(ls) != len(lines_all):
            errors.append(f"line_shots needs {len(lines_all)} lists (one per narration line plus the outcome), has {len(ls)}")
        for i, (line, shots) in enumerate(zip(lines_all, ls)):
            if not shots:
                errors.append(f"line {i + 1}: give it at least one shot")
                continue
            need = len(plain(line).split()) / WORDS_PER_SEC + 0.25
            have = sum(max(float(x["end"]) - float(x["start"]), 0) for x in shots) / 0.9
            if have < need:
                errors.append(f"line {i + 1}: shots cover about {have * 0.7:.1f}s but the line takes about {need:.1f}s")
            share = need / len(shots)
            short = [x for x in shots if float(x["end"]) - float(x["start"]) < 2.0]
            if short:
                warnings.append(f"line {i + 1}: shots under 2 seconds feel jumpy; use 2.2 to 3 second shots")
        flat = [x for shots in ls for x in shots]
    else:
        flat = spec["segments"]
    for i, s in enumerate(flat):
        a, b = float(s.get("start", -1)), float(s.get("end", -1))
        if not 0 <= a < b <= dur + 0.05:
            errors.append(f"segment {i + 1}: start/end outside the clip (0 to {dur})")
        speed = float(s.get("speed", 1.0))
        if not 0.5 <= speed <= 2.0:
            errors.append(f"segment {i + 1}: speed must be 0.5 to 2.0")
        if s.get("layout", "auto") not in ("auto", "fit", "crop"):
            errors.append(f"segment {i + 1}: layout must be auto, fit or crop")
        cx = float(s.get("crop_x", 0.5))
        if not 0 <= cx <= 1:
            errors.append(f"segment {i + 1}: crop_x must be 0 to 1")
        total += max(b - a, 0) / speed
    words = sum(len(plain(l).split()) for l in spec["narration"]) + len(plain(spec["outcome"]).split())
    long_segs = [] if spec.get("line_shots") else [i + 1 for i, sg in enumerate(flat) if (float(sg["end"]) - float(sg["start"])) / float(sg.get("speed", 1.0)) > 5.5]
    if long_segs:
        warnings.append(f"segments {long_segs} run over 5.5s; cut every 2 to 4 seconds to hold attention")
    est = words / WORDS_PER_SEC + 0.2 * (len(spec["narration"]) + 1) + 1.0
    if est > 170:
        errors.append(f"narration too long: about {est:.0f}s spoken; Shorts must stay under 3 minutes")
    elif est > 120:
        warnings.append(f"about {est:.0f}s spoken; past 2 minutes only if every line adds story and the footage carries it")
    if est < 14:
        warnings.append(f"narration is short ({est:.0f}s); Shorts under 15s rarely hold attention")
    if not spec.get("line_shots") and total < est + 1:
        errors.append(f"footage {total:.1f}s is shorter than estimated narration {est:.1f}s; add segments")
    return errors, warnings


def main(paths):
    bad = False
    for p in paths:
        errs, warns = validate(p)
        for w in warns:
            print(f"WARN  {p}: {w}")
        for e in errs:
            print(f"ERROR {p}: {e}")
        if errs:
            bad = True
        else:
            print(f"OK    {p}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
