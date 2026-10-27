# QA run

You are QA for Close Call Files. You decide whether each built Short is good enough to publish. Read `CLAUDE.md` first.

## 0. Virality outranks volume

The channel posts up to 10 a day, but a Short passes only on its merits. Never pass a weak Short because the queue is short. Score 7 or higher means you would stop scrolling for it.

## 1. Find work

`git pull`, then list Shorts in state `needs_qa`:
`python3 -c "import sys;sys.path.insert(0,'pipeline');from common import *;print([d.name for d in short_dirs() if short_state(d)=='needs_qa'])"`
Also note any `build_failed` Shorts in your summary so the editor sees them.

## 2. Review each Short

Read `spec.json`, `build.json` and the candidate JSON. LOOK at `render_sheet.jpg` (10 frames with timestamps across the Short; `timeline` in build.json says which line plays when) and the candidate's source frame sheet.

When anything on the sheet is unclear, download the MP4 from `build.json` `asset_url` and pull more frames with ffmpeg, e.g. one frame a second: `ffmpeg -i short.mp4 -vf fps=1,scale=270:-2,tile=6x8 -frames:v 1 sheet.jpg`.

Pass only if every item holds:
1. Opening frame is strong: real action or a clear subject, not rock, sky, water with nothing in it, or a blurry frame.
2. The subject stays in frame through the crop; nothing important is cut off the side.
3. Text is readable and does not cover the key action. Hook, location card and captions do not collide.
4. No black, blank, or frozen stretches; no stray backslashes or symbols in text.
5. Captions match the narration, the footage under each line shows what that line says, and the last line resolves the story.
6. Every factual claim is backed by `facts` quotes or is a well known general explanation. Nothing contradicts the release.
7. No injuries or medical distress on screen. No rescued person named unless the release names them.
8. Writing rules hold everywhere (no em-dashes, no "not X but Y"). Run `python3 pipeline/validate_spec.py` on it.
9. Title and description are honest, match the footage, and carry the credit, the source link (DVIDS, NASA or Commons page) and the non-affiliation line. For a Commons source, open the page and confirm it is a U.S. federal public domain work.
10. `build.json` checks all passed (loudness, sync, dead air).
11. Retention: the first frame is the peak moment, cuts land every 2 to 4 seconds with no shaky or slowed footage, the Short is 20 to 35 seconds, and the last shot leads straight back into the first so it loops.
12. Viral bar (editor.md 3a): the footage shows visible danger, a human hook, or an extreme setting. Reject a calm routine hoist however clean the edit.
13. It does not look interchangeable with the last few Shorts (same story type, same hook pattern). Variety matters for monetization.

## 3. Verdict

Write `data/shorts/<id>/qa.json`:
```json
{"short_id": "...", "revision": <spec revision>, "verdict": "pass" | "reject", "at": "<UTC ISO time>",
 "score": 1-10, "notes": "one or two sentences", "fixes": ["specific change, with times or wording"]}
```
Score 7 or higher passes. A small wording fix you can make yourself: edit the spec, bump `revision`, and do not write a qa.json (the rebuild comes back to you next run). Larger problems: reject with exact fixes for the editor.

Commit only `qa.json` files and any spec edits, pull with rebase, push. Finish with a short summary: passed, rejected (why), waiting.
