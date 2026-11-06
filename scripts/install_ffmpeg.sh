#!/usr/bin/env bash
# Install ffmpeg on a GitHub runner without hanging.
# apt has stalled for 18+ minutes on some runners (Nov 6, twice), so every apt call is time-boxed,
# the slow man-db trigger is switched off, and a static ffmpeg build is the fallback.
set -u
command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null && { ffmpeg -version | head -1; exit 0; }
sudo rm -f /var/lib/man-db/auto-update
echo 'man-db man-db/auto-update boolean false' | sudo debconf-set-selections 2>/dev/null || true
for i in 1 2; do
  sudo timeout 180 apt-get update -qq -o Acquire::Retries=2 -o Acquire::http::Timeout=20 &&
  sudo DEBIAN_FRONTEND=noninteractive timeout 300 apt-get install -y -qq --no-install-recommends ffmpeg ${EXTRA_PKGS:-} >/dev/null &&
  break
  echo "apt attempt $i failed or timed out"
done
if ! command -v ffmpeg >/dev/null; then
  echo "falling back to a static ffmpeg build"
  d=$(mktemp -d)
  timeout 300 curl -sSL --retry 3 -o "$d/ff.tar.xz" https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz &&
  tar xJf "$d/ff.tar.xz" -C "$d" && sudo cp "$d"/ffmpeg-*-static/ffmpeg "$d"/ffmpeg-*-static/ffprobe /usr/local/bin/
fi
ffmpeg -version | head -1
