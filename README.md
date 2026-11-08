# Merlin Plugins

The plugin registry for [Merlin](https://github.com/merlin-editor/merlin).
Merlin installs from it by name:

```sh
merlin plugin search json
merlin plugin install json
merlin plugin update
```

## How it works

Each file in [`plugins/`](plugins) names a plugin's source: a public git
repository, the folder in it, and a pinned commit for each version. Plugin
source never lives here.

When a version is added on `main`, [Publish](.github/workflows/publish.yml)
builds that commit in a container pinned by digest, packs it with
`merlin plugin pack`, attaches the `.merlin` file to a release named
`<name>-v<version>`, and signs a new `index.json` onto the `gh-pages` branch.
GitHub Pages serves it at https://merlin-editor.github.io/plugins/index.json,
with `index.json.minisig` beside it.

Merlin checks the index's signature against the keys in [`keys/`](keys), which
it ships with. It also checks that the index hasn't expired and isn't older than
one it has seen, then checks each download's SHA-256 against the index. Every
build is reproducible: building the same commit with the same tools gives the
same bytes, and [Check](.github/workflows/check.yml) builds each new version
twice to make sure.

The full design is in
[docs/plugin-registry.md](https://github.com/merlin-editor/merlin/blob/main/docs/plugin-registry.md).

## Adding a plugin

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Building one yourself

The registry builds at `/build/src` inside the container, because grammars'
C code doesn't build to the same bytes from different folders. To check a
package against the registry's:

```sh
docker run --rm -it -v "$PWD:/registry" -w /registry \
  rust:1.97.1-slim-trixie@sha256:8e8cf8f7fd54a2d23d5a743b3a03f56e26b6c774276c33fa0595111704ebb15c sh -c '
  apt-get update -q && xargs -a build/apt.txt apt-get install -y -q --no-install-recommends &&
  build/setup.sh && PATH=/opt/merlin/bin:$PATH python3 tools/registry.py build rust 0.1.0 /tmp/out &&
  cat /tmp/out/record.json'
```
