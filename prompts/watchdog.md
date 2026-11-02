# Watchdog run

You keep Close Call Files posting 10 viral Shorts a day with no help from Charles. You run at the start of every QA run (three times a day), and on your own when scheduled. Read `CLAUDE.md` first. Most runs should find everything healthy and end in a few minutes; when something is wrong, you fix it yourself.

## 1. Check

`git pull`. Then measure:

```
python3 - <<'EOF'
import sys, json; sys.path.insert(0, 'pipeline')
from common import *; from datetime import timedelta, datetime
import collections
now = now_utc()
c = collections.Counter(short_state(d) for d in short_dirs())
sched = 0
for d in short_dirs():
    if short_state(d) == 'uploaded':
        u = load_json(d / 'upload.json') or {}
        t = u.get('publish_at')
        if t and now < datetime.fromisoformat(t.replace('Z', '+00:00')) <= now + timedelta(hours=36):
            sched += 1
print(dict(c), 'scheduled next 36h:', sched)
EOF
```

Also read `data/upload_last.json`, `data/upload_limit.json`, `data/harvest_last.json`, the last 10 entries of `data/alerts.json`, every `build.json` with status error from the last 24 hours, and `git log --since="30 hours ago" --oneline` (are harvest, build, upload and stats runs still landing?). If GitHub workflow runs are needed, `gh api repos/charlesheathpro/close-call-files/actions/runs?per_page=20` works.

Healthy means all of these hold:
- scheduled in the next 36 hours + passed >= 15
- needs_build + needs_qa + passed + scheduled >= 25
- an upload run landed in the last 3 hours, a harvest in the last 30 hours, stats in the last 30 hours
- no build error repeated on 3 or more Shorts in the last 24 hours
- no `auth` or `upload_error` alert in the last 24 hours

If healthy: write one line to `data/watchdog.json` (`{"at", "healthy": true, "numbers": {...}}`), commit, push, finish with one line.

## 2. Fix

Work through what failed, in this order:

- **A systemic build failure** (the same error on 3+ Shorts): read the error and `pipeline/build.py`, fix the cause in code, test locally on one Short (`python3 pipeline/build.py <id>` with the needed env if available, or reproduce the failing step), push, and add the failed IDs to `triggers/build-ids` plus `date > triggers/build` to rebuild them (empty `triggers/build-ids` in a later commit). If the error is an ElevenLabs quota or 401, that needs Charles: say so in the first line of your summary.
- **Workflows not running** (GitHub sometimes skips scheduled runs): start them with a push to `triggers/<name>` (`date > triggers/upload`, `triggers/harvest`, `triggers/stats`, `triggers/build`).
- **Not enough Shorts**: do an editor pass yourself, following `prompts/editor.md` in full (playbook, viral bar, 3b, `validate_spec.py` and `preview_shots.py` clean), until needs_build + needs_qa + passed reaches 25 or good clips run out. If clips run out, push `archive` to `triggers/harvest` (`echo "archive $(date -u +%FT%T)" > triggers/harvest`). Then wait for the builds (poll `git pull` every 2 minutes, up to 30 minutes) and do a QA pass following `prompts/qa.md`, fixing near misses yourself.
- **Passed Shorts waiting but nothing uploading**: read `data/upload_limit.json`; if no limit is active, push `date > triggers/upload`.
- **Sign-in or upload errors**: YouTube auth problems need Charles; put them in the first line.

Keep the quality bar: never pass a Short below 7 to fill a slot. Never touch the Critical Incident channel, its Control Room, or anything on Charles's computer.

## 3. Record

Write `data/watchdog.json` with what you found and what you fixed. Commit only what you changed, pull with rebase, push. Finish with a short summary; if anything needs Charles, make it the first line.
