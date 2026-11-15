#!/bin/sh
# Checks the published index.json: that a key in keys/ signed it, and how
# many whole days it has before it expires, which it prints.
# INDEX_URL names another index; KEYS another set of .pub files.
set -eu
url=${INDEX_URL:-https://merlin-editor.github.io/plugins/index.json}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
curl -fsSL "$url" -o "$tmp/index.json"
curl -fsSL "$url.minisig" -o "$tmp/index.json.minisig"
signed=
for key in ${KEYS:-keys/*.pub}; do
    if minisign -Vq -m "$tmp/index.json" -x "$tmp/index.json.minisig" -p "$key" 2>/dev/null; then
        signed=1
        break
    fi
done
if [ -z "$signed" ]; then
    echo "::error::$url isn't signed by any key in keys/" >&2
    exit 1
fi
python3 - "$tmp/index.json" <<'PY'
import json, sys
from datetime import datetime, timezone
doc = json.load(open(sys.argv[1]))
expires = datetime.strptime(doc["expires"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
print(int((expires - datetime.now(timezone.utc)).total_seconds() // 86400))
PY
