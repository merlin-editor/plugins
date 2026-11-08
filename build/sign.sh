#!/bin/sh
# Writes index.json from the entries and the records in pages/, one serial
# on, signs it, and pushes gh-pages.
set -eu
cd "$(dirname "$0")/.."
python3 tools/registry.py index pages/records pages/index.json pages/index.json.next
mv pages/index.json.next pages/index.json
serial=$(python3 -c 'import json; print(json.load(open("pages/index.json"))["serial"])')
key=$(mktemp)
trap 'rm -f "$key"' EXIT
printf '%s\n' "$MINISIGN_SECRET_KEY" > "$key"
minisign -S -s "$key" -m pages/index.json -x pages/index.json.minisig \
    -t "merlin-editor/plugins index.json serial $serial"
rm -f "$key"
cd pages
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add -A
git commit -q -m "Index $serial"
git push -q origin HEAD:gh-pages
# Pages may not rebuild for a push made with the workflow's token.
gh api -X POST "repos/${GITHUB_REPOSITORY:-merlin-editor/plugins}/pages/builds" >/dev/null || true
echo "Published index $serial"
