"""Render one Short in several ElevenLabs voices and post them to the 'samples' release."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import SHORTS, WORK, config, run, save_json, DATA  # noqa: E402
from build import build_one  # noqa: E402

VARIANTS = [
    ("brian-v2", "nPczCjzI2devNBz1zQrb", "eleven_multilingual_v2"),
    ("adam-v2", "pNInz6obpgDQGcFmaJgB", "eleven_multilingual_v2"),
    ("bill-v2", "pqHfZKP75CvOlQylNhV4", "eleven_multilingual_v2"),
    ("eric-v2", "cjVigY5qzO86Huf0OWal", "eleven_multilingual_v2"),
    ("brian-flash", "nPczCjzI2devNBz1zQrb", "eleven_flash_v2_5"),
]


def main():
    short_id = sys.argv[1] if len(sys.argv) > 1 else "ccf-test-001"
    cfg = config()
    out = WORK / "samples"
    out.mkdir(parents=True, exist_ok=True)
    if subprocess.run(["gh", "release", "view", "samples"], capture_output=True).returncode != 0:
        run(["gh", "release", "create", "samples", "--title", "Voice and style samples", "--notes", "Review renders."])
    results = []
    for name, vid, model in VARIANTS:
        vcfg = {"engine": "elevenlabs", "voice_id": vid, "model_id": model, "speed": 1.0}
        try:
            r = build_one(SHORTS / short_id, vcfg, cfg, upload=False)
            dest = out / f"{short_id}-{name}.mp4"
            shutil.copy(r["local_path"], dest)
            run(["gh", "release", "upload", "samples", dest, "--clobber"])
            results.append({"name": name, "status": r["status"], "duration": r["duration"],
                            "failed": r["failed_checks"], "file": dest.name})
        except Exception as e:
            results.append({"name": name, "status": "error", "error": str(e)[:400]})
        print(results[-1])
    save_json(DATA / "voice_samples.json", {"short_id": short_id, "results": results})


if __name__ == "__main__":
    main()
