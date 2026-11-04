# Playbook (computed 2026-11-04T10:43:25Z from 43 Shorts older than 48 hours)

Written every night by pipeline/learn.py from the channel's own numbers. Positive effect means Shorts with that feature beat the channel average (score mixes views, average percent watched and subscribers per 1,000 views).

## Do more of
- source: nasa (+0.76, 3 Shorts)
- spacecraft or test story (+0.76, 3 Shorts)
- lane: aviation_naval (+0.64, 4 Shorts)
- story: splashdown recovery (+0.53, 1 Shorts)
- story: capsized boat, people in the water (+0.52, 1 Shorts)
- story: launch abort test (+0.5, 1 Shorts)
- music: aviation (+0.45, 2 Shorts)
- hook names a child (+0.26, 7 Shorts)

## Do less of
- music: hazards (-0.66, 4 Shorts)
- story: volcano eruption (-0.56, 2 Shorts)
- source: dvids (-0.56, 34 Shorts)
- lane: hazards (-0.52, 3 Shorts)
- story: wildfire rescue (-0.33, 1 Shorts)
- story: capsized yacht hoist (-0.27, 1 Shorts)
- length 45 s or more (-0.27, 2 Shorts)
- story: cliff hoist (-0.26, 1 Shorts)

## Best Shorts
- Orion splashes down after the Moon: 9395 views, 96% watched
- Boat flipped with a 4-year-old aboard: 18724 views, 78% watched
- Capsule torn off a rocket at Mach 1: 5249 views, 97% watched
- Dog fell off an Oregon sea cliff: 1289 views, 84% watched
- Lifted off a roof in Harvey's floodwater: 1394 views, 91% watched

## Weakest Shorts
- Lava fountains roar out of Kilauea: 444 views, 67% watched
- Hiker hurt on an Oregon sea cliff: 829 views, 48% watched
- Yacht broke in two on Lake Erie: 1220 views, 37% watched
- 214 people trapped by a wildfire: 341 views, 61% watched
- Mauna Loa erupts after 38 years: 145 views, 66% watched

## QA rejections this week (do not repeat these)
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
- ccf-20261103-03: Strong number, but the diver is never seen alone in the water: render 5 to 17s is twelve seconds of empty sea with the swimmer's fins at the door edge, the basket is a speck for most of 20 to 30s, and the hoist itself is calm. This is the routine door-cam basket hoist the viral bar rules out, and th
- ccf-20261104-01: Rev 2 render is clean (empty-sky shot gone), but it is interchangeable with ccf-20261102-07, two men on a capsized hull off Florida, which publishes today Nov 4 19:00Z. Hold, do not drop: the footage is strong.
- ccf-20261104-03: Calm top-down hoist from a riverbank with no visible danger; line 1 says 'This man' over a Coast Guard crewman. Fails the viral bar for a routine hoist.

## Changed tonight
- lane_mix {'rescue': 0.4, 'aviation_naval': 0.5, 'hazards': 0.1} -> {'rescue': 0.3, 'aviation_naval': 0.6, 'hazards': 0.1}
- query weights for 28 searches
