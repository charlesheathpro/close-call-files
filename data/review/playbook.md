# Playbook (computed 2026-11-27T11:57:37Z from 234 Shorts older than 48 hours)

Written every night by pipeline/learn.py from the channel's own numbers. Positive effect means Shorts with that feature beat the channel average (score mixes views, average percent watched and subscribers per 1,000 views).

## Do more of
- music: naval (+0.62, 12 Shorts)
- story: three fishermen in a life raft in heavy seas after their boat capsized, cutter crew throws a line (+0.58, 1 Shorts)
- story: man in floodwater among submerged cars, rescuer lowered on the cable, hoist into the helicopter (+0.52, 1 Shorts)
- story: army engineers' demolition training ends in a record blast (+0.4, 1 Shorts)
- story: pararescue team parachutes from an hc-130j into the open north pacific to reach a sick sailor (+0.39, 1 Shorts)
- story: nasa engineer rides the back seat of an f/a-18: afterburner takeoff, roll and loop, cockpit camera (+0.38, 1 Shorts)
- story: three men on a capsized hull in open water, life ring and line to a rescue boat (+0.38, 1 Shorts)
- story: tsunami ghost ship sunk by coast guard cutter gunfire (+0.36, 1 Shorts)

## Do less of
- lane: hazards (-0.54, 4 Shorts)
- story: dog hoist from sinking boat (-0.52, 1 Shorts)
- story: historic rocket test stand implosion (-0.47, 1 Shorts)
- story: missing boaters clinging to a capsized hull (-0.45, 1 Shorts)
- story: crab boat sinks at night, two men in a life raft, infrared, helicopter hoists (-0.44, 1 Shorts)
- story: hurricane flood day, kids, elders and dogs airlifted by helicopter crews (-0.41, 1 Shorts)
- story: volcano eruption (-0.39, 2 Shorts)
- story: security camera catches a tornado strike (-0.38, 1 Shorts)

## Best Shorts
- Raft in heavy seas, 40 miles out: 160924 views, 102% watched
- Cars underwater, a man in the flood: 919 views, 203% watched
- Biggest blast on an Army base in 10 years: 23970 views, 90% watched
- Parachuting to a sick sailor at sea: 47866 views, 79% watched
- Flipped hull 11 miles out, 3 men on top: 47530 views, 81% watched

## Weakest Shorts
- Florence: 67 people, 12 pets in one day: 131 views, 45% watched
- Crab boat sank at night off Washington: 95 views, 45% watched
- Clinging to a flipped boat 12 miles out: 33 views, 64% watched
- Saturn V test tower comes down: 59 views, 49% watched
- Dog hoisted from a sinking catamaran: 14 views, 67% watched

## QA rejections this week (do not repeat these)
- ccf-20261120-16: Strong MICLIC blast, but the Short is 12.8 s from a 15.7 s source and cannot reach 20 s without reused shots. Dropped.
- ccf-20261120-18: Clean footage of an LC-130 on the Greenland ice, but it is routine training with no visible danger, repeated head-on taxi shots, and an ending that does not show the climb-out clearly. Dropped.
- ccf-20261120-22: Source is one static 67-second hover shot of the Portuguese helicopter over the deck; nothing on screen shows the explosion, the parachute drop or the airlift, so every line plays over the same frame and it cannot hold retention.
- ccf-20261120-25: Hoist-cam footage is washed out and heavily artifacted, the opening is a blurry overexposed deck, the last 6 seconds repeat one angle, and there is no visible danger; source quality cannot be fixed by recutting.
- ccf-20261121-07: Clean hoist-camera footage with a swimmer swinging over the wake, but it is the seventh moving-fishing-boat hoist in two days (20-27, 20-28, 20-29, 20-30, 21-04, 21-05) and its title and hook nearly repeat 20-30. Fails item 13 (interchangeable).
- ccf-20261121-08: Third Saturn V liftoff in this batch (21-02 Apollo 11 engines, 21-06 Apollo 4) and the cloud/sound barrier lines play over shots with no condensation cloud (the cloud only appears in the 0 to 4 s opener). No danger and a weak resolution; 21-06 tells the stronger Saturn V story.
- ccf-20261121-16: Footage is a CG animation made before the test, presented as the real flight. Dropped.
- ccf-20261121-18: Clean, well-cropped 16mm launch footage, but it is the fourth Artemis II liftoff angle in the queue and shows a routine launch with no visible danger.
- ccf-20261122-01: r3 removed the animation opener and the interview cut-ins, but the real footage is hazy and distant: the liftoff is a speck for 8 seconds and the in-air capsule shots are pale and repetitive. No visible danger at Short scale, and a pad abort already ran as ccf-20261121-16.
- ccf-20261122-04: Third F/A-18 incentive ride in this batch with the same hook pattern, and the weakest one: the opener is a calm back-seat shot with sky and no visible maneuver. Interchangeable with -05 and -06.
- ccf-20261122-10: No danger or close call: a photographer's T-38 ride, mostly cockpit selfies and a ladder shot after the opening formation, and nothing on screen backs the 'landed with every camera still rolling' outcome.
- ccf-20261122-14: Calm record flight with no danger on screen; about ten seconds on the same altimeter dial, and it is the third X-15 Short from the same documentary in this batch.
- ccf-20261122-18: Calm blue-sky basket transfer with no visible danger; most of the 30 s is the same underside shot of the Jayhawk from a rain-spotted lens, and the 33 s source has nothing else to cut to. Dropped.
- ccf-20261122-22: About 35 seconds of grey lunar surface through the LM window with nothing changing; the computer alarms are only narrated, never seen, and the last shot is a letterboxed quarantine room.
- ccf-20261122-27: One continuous helicopter shot of a normal, uneventful launch for the whole Short; no danger, no turn, and the rocket is small in the frame.

## Changed tonight
- lane_mix {'rescue': 0.19, 'aviation_naval': 0.71, 'hazards': 0.1} -> {'rescue': 0.15, 'aviation_naval': 0.75, 'hazards': 0.1}
- query weights for 81 searches
