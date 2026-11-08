#!/bin/sh
# On main: builds each version that has no record on gh-pages yet,
# attaches it to a release, records it, then writes and signs index.json.
# Expects gh-pages checked out in pages/.
set -eu
cd "$(dirname "$0")/.."
repo=${GITHUB_REPOSITORY:-merlin-editor/plugins}
python3 tools/registry.py pending pages/records |
    python3 -c 'import json,sys; [print(v["name"], v["version"]) for v in json.load(sys.stdin)]' |
while read -r name version; do
    out="/tmp/out/$name-$version"
    file="$name-$version.merlin"
    tag="$name-v$version"
    python3 tools/registry.py build "$name" "$version" "$out"
    if gh release view "$tag" --repo "$repo" >/dev/null 2>&1; then
        # A run that stopped after releasing: what's there must be what
        # this build made, since builds are reproducible.
        rm -rf /tmp/existing
        gh release download "$tag" --repo "$repo" --pattern "$file" --dir /tmp/existing
        if ! cmp -s "/tmp/existing/$file" "$out/$file"; then
            echo "::error::$tag is already released with different bytes; a published version never changes"
            exit 1
        fi
    else
        commit=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["commit"])' "$out/record.json")
        gh release create "$tag" "$out/$file" --repo "$repo" --target main \
            --title "$name $version" --notes "Built from $commit by the registry."
    fi
    mkdir -p "pages/records/$name"
    cp "$out/record.json" "pages/records/$name/$version.json"
done
build/sign.sh
