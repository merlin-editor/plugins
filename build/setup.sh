#!/bin/sh
# Gets a build ready inside the pinned container: the wasm target, and the
# merlin whose `merlin plugin pack` makes the packages.
set -eu
cd "$(dirname "$0")/.."
. build/toolchain.env
git config --global --add safe.directory '*'
rustup target add wasm32-wasip2
if [ ! -x /opt/merlin/bin/merlin ]; then
    cargo install --locked --quiet --root /opt/merlin \
        --git https://github.com/merlin-editor/merlin --rev "$MERLIN_REV" merlin
fi
echo /opt/merlin/bin >> "${GITHUB_PATH:-/dev/null}"
/opt/merlin/bin/merlin --version
