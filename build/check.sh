#!/bin/sh
# For a pull request: builds each new version twice, from scratch, and
# fails unless both give the same bytes. Writes what each asks for to the
# job summary.
set -eu
cd "$(dirname "$0")/.."
summary=${GITHUB_STEP_SUMMARY:-/dev/stdout}
echo "$VERSIONS" | python3 -c 'import json,sys; [print(v["name"], v["version"]) for v in json.load(sys.stdin)]' |
while read -r name version; do
    for run in a b; do
        python3 tools/registry.py build "$name" "$version" "/tmp/out/$run/$name-$version"
    done
    a=$(sha256sum "/tmp/out/a/$name-$version/$name-$version.merlin" | cut -d' ' -f1)
    b=$(sha256sum "/tmp/out/b/$name-$version/$name-$version.merlin" | cut -d' ' -f1)
    if [ "$a" != "$b" ]; then
        echo "::error::$name $version built twice gave different bytes ($a, $b)"
        exit 1
    fi
    python3 tools/registry.py summary "/tmp/out/a/$name-$version/record.json" >> "$summary"
done
