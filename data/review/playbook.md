# Playbook (computed 2026-11-03T10:40:34Z from 40 Shorts older than 48 hours)

Written every night by pipeline/learn.py from the channel's own numbers. Positive effect means Shorts with that feature beat the channel average (score mixes views, average percent watched and subscribers per 1,000 views).

## Do more of
- source: nasa (+0.72, 3 Shorts)
- spacecraft or test story (+0.72, 3 Shorts)
- lane: aviation_naval (+0.62, 4 Shorts)
- story: launch abort test (+0.49, 1 Shorts)
- story: capsized boat, people in the water (+0.48, 1 Shorts)
- story: splashdown recovery (+0.48, 1 Shorts)
- music: aviation (+0.45, 2 Shorts)
- hook names a child (+0.26, 6 Shorts)

## Do less of
- music: hazards (-0.65, 4 Shorts)
- source: dvids (-0.57, 31 Shorts)
- story: volcano eruption (-0.5, 2 Shorts)
- lane: hazards (-0.46, 3 Shorts)
- story: wildfire rescue (-0.39, 1 Shorts)
- length 45 s or more (-0.31, 2 Shorts)
- story: cliff hoist (-0.27, 1 Shorts)
- story: capsized yacht hoist (-0.26, 1 Shorts)

## Best Shorts
- Capsule torn off a rocket at Mach 1: 5248 views, 97% watched
- Orion splashes down after the Moon: 9343 views, 92% watched
- Boat flipped with a 4-year-old aboard: 18410 views, 74% watched
- Dog fell off an Oregon sea cliff: 1288 views, 84% watched
- Lifted off a roof in Harvey's floodwater: 1394 views, 91% watched

## Weakest Shorts
- Lava fountains roar out of Kilauea: 447 views, 74% watched
- Yacht broke in two on Lake Erie: 1219 views, 37% watched
- Hiker hurt on an Oregon sea cliff: 824 views, 46% watched
- 214 people trapped by a wildfire: 342 views, 50% watched
- Mauna Loa erupts after 38 years: 145 views, 66% watched

## QA rejections this week (do not repeat these)
- ccf-20261027-05: The surf under the stilt house is real danger, but the 366x274 FLIR source sits as a small, washed-out strip in the middle of a blurred frame for all 28 seconds, and line 3 plays over six seconds of a static wall. It would also be the fourth flooded-house rescue in a row after 01, 02 and 08.
- ccf-20261028-03: The source is a USCG vertical Short with the real picture in a thin middle band and blur filling the rest, so the Short looks small and soft. The opening is a grainy gray FLIR frame, the basket line (7 to 9s) sits on dark blur, and the cabin shots (12 to 15s) are washed out. No visible danger surviv
- ccf-20261028-04: Calm, routine night hoist from a disabled sailboat with no injuries and no visible danger, shown as a small letterboxed thermal window over a blurred fill; it fails the viral bar and is one more sea hoist in a buffer that is already almost all rescue.
- ccf-20261028-09: Now 25s, but render 9.3 to 17.5s (source 9.3 to 18.0) is about 8 seconds of riders' legs dangling over palm trees; the riders are above the top edge of the source frame there, so no crop_x can fix it (check 2 and 11 fail). The strong footage (source 0.2 to 9.3 and 18.0 to 28.4) only carries about 19
- ccf-20261029-04: Best opening flames of the batch, but the payoff is never on screen: 'All seven were pulled from the raft' plays over the cutter and an empty-looking raft, and 8 to 14s is a soft, distant boat half cut off by the crop. It is also the third burning-boat-and-raft story in two days (29-03 and 29-05 cov
- ccf-20261030-01: Outcome 'to dry ground' is not in the release and is not shown, and the last 4 seconds are empty sky with a helicopter under a line about the truck. Calm wading also reads as the 4th Harvey flood Short this week.
- ccf-20261030-02: Handheld cabin footage is shaky and hard to read: 14 to 23s is mostly the basket rail and crew backs, and the roof shot (10 to 13s) is a pixelated digital zoom. Third Harvey Short in two days (29-02 uploaded, 30-01 and 30-03 queued).
- ccf-20261030-03: The hoist-camera angle is novel, but the footage is low resolution with fisheye blur and color artifacts, and all 30 seconds are the same overhead roof view, so nothing new happens after the first 5 seconds. Also another Harvey hoist beside 29-02 and 30-01.
- ccf-20261030-04: Beautiful footage, but it is the third lava Short in four days and the same 2018 Kilauea eruption as ccf-20261030-06, which publishes Nov 1, so it looks interchangeable. The script also has no stakes: line 2 just repeats the location card and nothing says what was at risk.
- ccf-20261030-05: First jets on a new carrier is a milestone with no danger and no close call, and three shots are empty or wrong: blank sky at 8.5s, a jet cut off the left edge at 13.5s, an empty deck at 23.7s under 'Then a Super Hornet landed next.'
- ccf-20261030-07: Calm, routine basket hoist from door-cam footage with heavy color noise. The boat never looks like it is taking on water and the dog is not clearly seen, so the danger in the hook is not visible.
- ccf-20261030-08: Better: the impact opener and second angle land. Still a 5-second static wide of the tripod with the craft tiny in the sky (render 16.5 to 21.5s), an empty pad before the second drop (21.7 to 23.5s), and the outcome 'crumpled wreck' plays over spectators behind a fence (33 to 35s).
- ccf-20261030-09: Strong hook number, but it is one slow, nearly static ISS view for 36 seconds, letterboxed small in the middle of a blurred background, with the solar array cutting into frames at 9.2s and 14.7s.
- ccf-20261030-10: The hook promises a 3,000 gallon drop that never appears on screen, and the title says it flies into the smoke, which the footage does not show. It is also the same C-130 over a wildfire story as 27-76.
- ccf-20261031-04: The footage never shows the danger the narration claims: a small distant sailboat through a rain-spotted window, seas that look moderate, empty water at 8 to 11.5s and 16 to 17.5s, and the hoist is a red blur at 22 to 23.5s. A calm-looking hoist fails the viral bar.

## Changed tonight
- lane_mix {'rescue': 0.4, 'aviation_naval': 0.5, 'hazards': 0.1} -> {'rescue': 0.3, 'aviation_naval': 0.6, 'hazards': 0.1}
- query weights for 25 searches
