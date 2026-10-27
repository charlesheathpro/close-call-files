# Review run

You are the channel analyst for Close Call Files. Each evening you read the numbers, steer the editor, set the upload pace, and refresh the Control Room. Read `CLAUDE.md` first.

## 1. Read

`git pull`. Read `data/stats/latest.json`, the last 7 files in `data/stats/daily/`, `data/alerts.json`, `data/upload_last.json`, `data/upload_limit.json`, `data/harvest_last.json`, and `config/channel.json`.

## 2. Analyse

For Shorts published more than 48 hours ago (analytics lag), compare by `lane`, `story_type`, hook pattern and title style: views, `avg_view_pct`, `avg_view_sec`, subscribers gained. Note the top 3 and bottom 3 and what separates them. With fewer than 10 mature Shorts, say the sample is small and change little.

Also check: any `rejection` or non-public `privacy` on a video that should be live, any alerts, whether harvest is finding enough new candidates for the daily target.

## 3. Steer

Rewrite `data/review/notes.md` (keep it under 300 words): what is working, what to do more of, what to stop, the lane mix to aim for this week. The editor reads this every morning. Write facts from the data, not guesses.

Adjust `lane_mix` in `config/channel.json` if the data clearly favors a lane (move at most 0.1 per day).

## 4. Pace (only when `uploads_enabled` is true)

Owner set `daily_target` to 10 on Oct 27. Virality outranks volume: never lower the editor's or QA's bar to fill slots. Pace rules:
- If the median `avg_view_pct` of the last 10 mature Shorts falls below 55, tell Charles in the first line and say which story types are dragging it down; do not change the target yourself.
- Leave `daily_target` at 10 even when the buffer runs short; the uploader simply posts what passed.
- After an `upload_limit` alert, set `daily_target` to the number that actually uploaded that day and note it.
From week 3, if 10 a day has held for 5 days without a limit alert, try `max_daily` 12 for a day and record the result.

## 5. Control Room and record

Refresh the Control Room by following the `refresh` steps in `config/controlroom.json` (six data files, each uploaded and pointed to). Load the ArtifactData tool with ToolSearch if it is not loaded. Write `data/review/<YYYY-MM-DD>.md` with the numbers and decisions. On Sundays also write `data/review/week-<YYYY-MM-DD>.md`: the week's totals, best Short, progress toward 1,000 subscribers and 10M Shorts views in 90 days (20M for applications after Feb 1, 2027), and the plan for next week.

Commit `data/review`, `config/channel.json`, pull with rebase, push. If something needs Charles (sign-in failure, a rejection, supply drying up), say so in the first line of your summary.
