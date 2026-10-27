"""Validate a Short spec before it is committed or built.

Usage: python pipeline/validate_spec.py data/shorts/<short_id>/spec.json [...]
Exit code 1 if any spec has errors. The editor task runs this before pushing.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CANDIDATES, load_json, writing_problems  # noqa: E402

LANES = {"rescue", "aviation_naval", "hazards"}
WORDS_PER_SEC = 2.6  # Kokoro at speed 1.08, measured roughly


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def validate(spec_path):
    errors, warnings = [], []
    spec = load_json(spec_path)
    if spec is None:
        return [f"cannot read {spec_path}"], []
    req = ["short_id", "revision", "candidate_id", "lane", "story_type", "hook", "narration", "outcome",
           "location_card", "segments", "title", "description", "tags", "question_comment", "facts"]
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
    if not isinstance(spec["narration"], list) or not 2 <= len(spec["narration"]) <= 9:
        errors.append("narration must be a list of 2 to 9 lines")
    for i, line in enumerate(spec["narration"]):
        if len(line) > 170:
            errors.append(f"narration line {i + 1} over 170 characters")
    if len(spec["outcome"]) > 150:
        errors.append("outcome over 150 characters")
    if len(spec["title"]) > 95:
        errors.append("title over 95 characters")
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
    texts = {"hook": spec["hook"], "outcome": spec["outcome"], "title": spec["title"],
             "description": spec["description"], "question_comment": spec["question_comment"],
             "location": lc.get("place", "")}
    for i, l in enumerate(spec["narration"]):
        texts[f"narration[{i + 1}]"] = l
    for name, t in texts.items():
        for p in writing_problems(t):
            errors.append(f"{name}: {p}")

    # The outcome must be spoken last and must actually resolve
    if norm(spec["narration"][-1]) == norm(spec["outcome"]):
        errors.append("do not repeat the outcome as the last narration line; the build speaks the outcome itself")
    if re.search(r"\b(?:will|unclear|unknown|remains to be seen|stay tuned|part 2|to be continued)\b", spec["outcome"], re.I):
        errors.append("outcome must state how it ended, in past tense, with no cliffhanger")

    # Grounding: every fact quote must appear in the agency release or transcript
    source_text = norm(" ".join([cand.get("title") or "", cand.get("description") or "",
                                 " ".join(s["text"] for s in cand.get("transcript", []))]))
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
    for i, s in enumerate(spec["segments"]):
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
    words = sum(len(l.split()) for l in spec["narration"]) + len(spec["outcome"].split())
    est = words / WORDS_PER_SEC + 0.2 * (len(spec["narration"]) + 1) + 1.0
    if est > 57:
        errors.append(f"narration too long: about {est:.0f}s spoken, keep it under 55s")
    if est < 14:
        warnings.append(f"narration is short ({est:.0f}s); Shorts under 15s rarely hold attention")
    if total < est + 1:
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
