# Close Call Files

Fully automated YouTube Shorts channel (@officialclosecall): real rescues and close calls told in under a minute from public-domain U.S. government footage (DVIDS). Everything runs in the cloud. Nothing depends on Charles's Mac.

## How a Short moves through the system

| Stage | Runs on | Reads | Writes |
|---|---|---|---|
| Harvest | GitHub Actions `harvest.yml`, daily ~4 AM MT | DVIDS API | `data/candidates/<id>.json` + `.jpg` frame sheet |
| Editor | Claude scheduled task, `prompts/editor.md` | candidates, stats, review notes | `data/shorts/<short_id>/spec.json` |
| Build | GitHub Actions `build.yml`, on spec push + every 2 h | spec, source MP4 | `build.json`, `render_sheet.jpg`, MP4 on release `renders` |
| QA | Claude scheduled task, `prompts/qa.md` | spec, build, render sheet, MP4 | `qa.json` |
| Upload | GitHub Actions `upload.yml`, every 3 h | passed Shorts, `config/channel.json` | `upload.json`, YouTube video |
| Stats | GitHub Actions `stats.yml`, ~9 PM MT | YouTube Data + Analytics APIs | `data/stats/latest.json` |
| Review | Claude scheduled task, `prompts/review.md` | stats | `data/review/notes.md`, ramp in config, Control Room |

Status of a Short is derived from which files exist (`pipeline/common.py: short_state`): needs_build, build_failed, needs_qa, passed, rejected, uploaded, dropped. Every stage writes only its own file, so stages never overwrite each other.

To start a workflow from a push, change the matching file in `triggers/` (e.g. `date > triggers/harvest`). `triggers/build-ids` forces rebuilds of listed Short IDs; empty it afterwards.

## Non-negotiable rules for anything published

- No em-dashes, en-dashes or double hyphens. No "not X but Y", "isn't X, it's Y", or "more than just" phrasing. `pipeline/validate_spec.py` enforces this.
- Every Short resolves. The `outcome` field is a past-tense statement of how it ended, spoken as the last line (no on-screen outcome graphic). If the source does not say or show how it ended, the clip is not used.
- Facts about the incident come only from the agency release, the transcript, a cited press release (`extra_sources`), or what is plainly visible. Each claim needs a verbatim `source_quote`. General explanations (how a hoist works) must be accurate and well known.
- No names of rescued people unless the release names them, and even then prefer roles. No injuries or medical scenes on screen.
- Skip any asset with non-federal credit or copyright text (the harvester filters most). Every description credits the unit and links the DVIDS page, and states the channel is not affiliated with or endorsed by the U.S. government.
- Uploads stay off (`uploads_enabled: false`) until Charles approves samples.

## Commit etiquette

Pull with rebase before pushing. Only touch the files your stage owns. End commit messages with the attribution lines the session gives you.
