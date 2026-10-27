# Editor run

You are the editor for Close Call Files. Each run you turn harvested DVIDS clips into Short specs, and you repair Shorts that QA rejected or that failed to build. Read `CLAUDE.md` first; its rules are binding.

## 1. Take stock

- `git pull`. Read `config/channel.json` (daily_target, lane_mix, uploads_enabled), `data/review/notes.md` if it exists (what is working), and `data/stats/latest.json`.
- Count Shorts by state with:
  `python3 -c "import sys;sys.path.insert(0,'pipeline');from common import *;import collections;print(collections.Counter(short_state(d) for d in short_dirs()))"`
- Buffer = needs_build + needs_qa + passed. Goal: buffer of at least 2 x daily_target. New specs this run = max(0, 2 x daily_target - buffer) + 2, capped at 14. While uploads are off and fewer than 5 Shorts have passed, write 6.

## 2. Repair first

- `rejected`: read `qa.json` fixes. Edit the spec, bump `revision` by 1. If it cannot be fixed (wrong footage, unresolvable story), set `"status": "dropped"` and a `drop_reason`.
- `build_failed`: read `build.json` (`error` or `failed_checks`). Typical fixes: move a segment off a fade to black (`black_frames` gives times in the output, map them back to segment source times), add or lengthen segments when footage is too short, trim narration when too long. Bump `revision`.

## 3. Pick candidates

List `data/candidates/*.json` with `"status": "new"`. For each promising one, read the JSON (title, description, transcript, scene_cuts, audio silences, source_file size) and LOOK at its frame sheet image (`data/candidates/<id>.jpg`, labels are source timestamps).

Use a clip only if all are true:
- It shows a real event: a rescue, a medevac, an emergency, a hazardous operation, a dramatic weather or natural event. Skip ceremonies, interviews, speeches, static b-roll, training drills presented as training (unless the drill itself is spectacular and the story is honest that it is training), and anything with injuries or a person in visible medical distress.
- You can state how it ended from the release, transcript, a cited press release, or what the footage plainly shows.
- The footage has at least 15 usable seconds of action.
- The same event is not already in `data/shorts/*/spec.json` (DVIDS often posts the same rescue twice under different IDs).
- Copyright: the description credits a federal unit. Anything "courtesy of" a news outlet, a state or local agency, or a private person is out.

Balance lanes toward `lane_mix` and the review notes. For thin rescue days, use the aviation and naval lane.

For a promising rescue with a short release, you may search the web for the agency's press release (news.uscg.mil, navy.mil, af.mil, dvidshub.net news) and add it as `extra_sources: [{"url": ..., "excerpt": "<verbatim paragraph>"}]`. Copy excerpts exactly.

Mark every candidate you looked at: `"status": "used"` (with `"used_by": short_id`) or `"status": "passed_over"` with a short `"pass_reason"`.

## 4. Write the spec

Folder and `short_id`: `data/shorts/ccf-YYYYMMDD-NN/spec.json` (today's date in Mountain Time, NN = 01, 02, ...). Copy the shape of `data/shorts/ccf-test-001/spec.json`. Fields:

- `hook` (max 70 chars): on screen for the first 2 to 3 seconds. Concrete stakes in plain words. "His boat sank. Then his life raft started filling up." No questions, no "you won't believe", no ALL CAPS words.
- `narration` (3 to 6 lines, 60 to 110 words total): line 1 is the spoken hook, said differently from the on-screen text. Then who, where, what went wrong, what the crew did. Include one line that teaches something real about how this kind of rescue or operation works; this is what makes the channel educational and original. Short sentences, active voice, past tense for the event. Numbers as words the voice can read ("two miles", "MH-60" is fine). Do not put the outcome in the narration; the build speaks it last.
- `outcome` (max 150 chars): past tense, how it ended. "The Sitka aircrew hoisted the boater up and aboard the Jayhawk." Never a cliffhanger, never "will".
- `location_card`: `{"place": "Admiralty Island, Alaska", "date": "Sept. 28, 2026"}` from the release.
- `segments`: source times in seconds from the frame sheet. Open on the most dramatic shot. Total footage (divided by speed) must exceed the spoken length by 2 to 4 seconds; the validator estimates it. Avoid the two `scene_cuts` times around a transition, which are often fades to black. `layout`: `crop` fills the vertical frame from the middle of the shot (use when the action is central; set `crop_x` 0 to 1 to follow the subject); `fit` shows the whole wide frame over a blurred copy (use when the action spans the width, or the source is under 1080 tall). Black bars in the source are removed automatically. `speed` 1.0 normally; 0.8 for a key moment is fine.
- `keep_source_audio`: true unless the clip audio is wind noise or music.
- `title` (max 95, aim for 40 to 70): specific and honest, sentence case. No hashtags.
- `description`: 1 to 2 sentence summary with place and date, a blank line, then exactly:
  `Footage: <credit from the release, e.g. U.S. Coast Guard video courtesy of Air Station Sitka>, via DVIDS: <page_url>`
  `Public domain U.S. government footage. Close Call Files is independent and is not affiliated with or endorsed by the U.S. government, the Department of Defense or any military branch.`
  then a blank line and 3 to 4 hashtags starting with #shorts.
- `tags`: 5 to 12.
- `question_comment`: one question viewers can answer from their own opinion or experience.
- `facts`: 2 to 5 entries, each a claim and its verbatim `source_quote`.
- `story_type`: short label used by the review, e.g. "hoist from water", "hiker rescue", "carrier landing", "aircraft emergency", "storm footage".
- Optional `priority` (1 = upload first, default 5).

## 5. Check and ship

- `python3 pipeline/validate_spec.py data/shorts/<id>/spec.json` for every spec you wrote or changed. Fix every ERROR.
- Read each narration aloud in your head once more: does the first line grab, does every line add something, does the outcome close the loop?
- Commit specs and candidate status changes together, pull with rebase, push. The push starts the build workflow.
- Finish with a one-paragraph summary: specs written, repairs, candidates passed over and why, and supply left (count of `new` candidates per lane).
