#!/usr/bin/env bash
# Commit whatever changed and push, retrying on races with other writers.
set -euo pipefail
msg="$1"
git config user.name "close-call-files-bot"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add -A data config || true
if git diff --cached --quiet; then
  echo "nothing to commit"; exit 0
fi
git commit -m "$msg"
for i in 1 2 3 4 5; do
  if git push origin HEAD:main; then exit 0; fi
  git pull --rebase -X theirs origin main || { git rebase --abort || true; git pull --no-rebase -X ours origin main; }
  sleep $((i * 3))
done
echo "push failed after retries"; exit 1
