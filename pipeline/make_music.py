"""Generate the channel's original music library with ElevenLabs Music.

Each bed has two sections: a restrained tension section and a short warm lift.
The build lines the lift up with the outcome line. Tracks are original, so no
Content ID matches, and ElevenLabs paid plans clear them for commercial use.

Usage: python pipeline/make_music.py [track_id ...]   (default: every missing track)
"""
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, iso, load_json, save_json  # noqa: E402

MUSIC_DIR = ROOT / "assets" / "music"
TENSION_MS = 34000
LIFT_MS = 12000

GLOBAL_POS = ["cinematic documentary underscore", "instrumental", "no vocals", "restrained", "modern film score",
              "clean mix with space for a narrator", "steady tempo"]
GLOBAL_NEG = ["vocals", "choir", "lyrics", "spoken word", "EDM drop", "dubstep", "heavy distortion", "loud cymbal crashes",
              "comedy", "cartoonish"]

TRACKS = [
    {"id": "pulse-strings", "moods": ["rescue", "sea"],
     "tension": ["low pulsing synth bass", "muted string ostinato", "soft ticking percussion", "100 bpm", "minor key"],
     "lift": ["strings open into a warm major chord", "soft piano notes", "hopeful", "relief"]},
    {"id": "piano-heartbeat", "moods": ["rescue", "mountain"],
     "tension": ["sparse low piano", "heartbeat kick drum", "airy pad", "90 bpm", "minor key", "suspense"],
     "lift": ["piano moves to major", "warm cello", "gentle and grateful"]},
    {"id": "ocean-drone", "moods": ["sea", "rescue"],
     "tension": ["deep ambient drone", "slow rising synth", "subtle clock tick", "95 bpm", "tense"],
     "lift": ["bright pad swell", "soft guitar harmonics", "calm after the storm"]},
    {"id": "taiko-low", "moods": ["rescue", "storm"],
     "tension": ["low taiko hits", "tight string staccato", "dark synth bass", "105 bpm", "urgent but controlled"],
     "lift": ["horns and strings resolve to major", "warm", "triumphant but quiet"]},
    {"id": "rotor-electronic", "moods": ["aviation", "rescue"],
     "tension": ["modern electronic pulse", "filtered arpeggio", "tight electronic drums", "110 bpm", "focused"],
     "lift": ["synth chords open up", "major key", "uplifting", "soft"]},
    {"id": "jet-drive", "moods": ["aviation", "naval"],
     "tension": ["driving low strings", "electronic percussion", "steady eighth-note bass", "115 bpm", "determined"],
     "lift": ["full strings resolve", "brass swell", "proud", "not loud"]},
    {"id": "storm-front", "moods": ["storm", "hazards"],
     "tension": ["ominous low brass", "rumbling synth", "slow tom hits", "85 bpm", "foreboding"],
     "lift": ["choir-free string resolution", "major key", "relief", "wide"]},
    {"id": "night-search", "moods": ["rescue", "night", "sea"],
     "tension": ["cold ambient pads", "sonar-like plucks", "soft pulsing bass", "92 bpm", "searching"],
     "lift": ["warm piano and strings", "found", "gentle major key"]},
]


def compose(t):
    plan = {
        "positive_global_styles": GLOBAL_POS,
        "negative_global_styles": GLOBAL_NEG,
        "sections": [
            {"section_name": "tension", "positive_local_styles": t["tension"],
             "negative_local_styles": ["melody lead", "big drum fills"], "duration_ms": TENSION_MS, "lines": []},
            {"section_name": "lift", "positive_local_styles": t["lift"],
             "negative_local_styles": ["fast drums", "sudden stop"], "duration_ms": LIFT_MS, "lines": []},
        ],
    }
    r = requests.post("https://api.elevenlabs.io/v1/music", params={"output_format": "mp3_44100_192"},
                      headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
                      json={"composition_plan": plan, "model_id": "music_v1", "respect_sections_durations": True},
                      timeout=600)
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs music {r.status_code}: {r.text[:300]}")
    return r.content, r.headers.get("song-id")


def main(ids):
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    lib_path = MUSIC_DIR / "library.json"
    lib = load_json(lib_path, {"tracks": []})
    have = {t["id"] for t in lib["tracks"] if (MUSIC_DIR / t["file"]).exists()}
    todo = [t for t in TRACKS if (t["id"] in ids if ids else t["id"] not in have)]
    for t in todo:
        audio, song_id = compose(t)
        f = f"{t['id']}.mp3"
        (MUSIC_DIR / f).write_bytes(audio)
        lib["tracks"] = [x for x in lib["tracks"] if x["id"] != t["id"]]
        lib["tracks"].append({"id": t["id"], "file": f, "moods": t["moods"], "resolve_at": TENSION_MS / 1000,
                              "length": (TENSION_MS + LIFT_MS) / 1000, "source": "ElevenLabs Music (music_v1)",
                              "song_id": song_id, "made_at": iso()})
        save_json(lib_path, lib)
        print(f"made {f}")


if __name__ == "__main__":
    main(sys.argv[1:])
