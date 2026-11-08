#!/usr/bin/env python3
"""The registry's tools: check entries, build a plugin version into a
package, and write index.json. Standard library only (Python 3.11+).

  registry.py validate [--base REF]       check plugins/*.toml; with --base,
                                          that versions were only added, and
                                          print the new ones as JSON
  registry.py pending RECORDS             versions with no build record yet,
                                          as JSON
  registry.py build NAME VERSION OUT      clone, build and pack one version;
                                          writes the .merlin and record.json.
                                          It builds in $REGISTRY_SRC (default
                                          /build/src), emptied first
  registry.py index RECORDS OLD OUT       write index.json from the entries
                                          and records, one serial after OLD
  registry.py summary RECORD              what a build asks for, as Markdown

See docs/plugin-registry.md in merlin-editor/merlin.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRIES = ROOT / "plugins"
REGISTRY_REPO = os.environ.get("GITHUB_REPOSITORY", "merlin-editor/plugins")
NAME = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
VERSION = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(-[0-9A-Za-z]+(\.[0-9A-Za-z]+)*)?(\+[0-9A-Za-z]+(\.[0-9A-Za-z]+)*)?$"
)
COMMIT = re.compile(r"^[0-9a-f]{40}$")
ENTRY_KEYS = {"repository", "path", "owners", "blocked", "versions"}
VERSION_KEYS = {"version", "commit", "yanked", "blocked"}
EXPIRY = timedelta(days=30)
# The manifest fields Browse shows, copied into each record.
SHOWN = ("title", "description", "badge", "hue", "license")


def fail(message):
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def entries():
    """Every entry, by name."""
    found = {}
    for path in sorted(ENTRIES.glob("*.toml")):
        with open(path, "rb") as f:
            found[path.stem] = tomllib.load(f)
    return found


def check_entry(name, entry):
    """What's wrong with one entry, if anything."""
    problems = []
    if not NAME.match(name):
        problems.append(f"{name}: a name is 2-40 lowercase letters, digits and -, starting with a letter")
    if extra := set(entry) - ENTRY_KEYS:
        problems.append(f"{name}: unknown keys {sorted(extra)}")
    repo = entry.get("repository", "")
    if not re.match(r"^https://[^\s]+$", repo):
        problems.append(f"{name}: repository must be an https URL")
    if not isinstance(entry.get("path", ""), str) or ".." in entry.get("path", "").split("/"):
        problems.append(f"{name}: path must be a folder in the repository")
    owners = entry.get("owners", [])
    if not owners or not all(isinstance(o, str) and o for o in owners):
        problems.append(f"{name}: owners must list at least one GitHub login")
    seen = set()
    for v in entry.get("versions", []):
        if extra := set(v) - VERSION_KEYS:
            problems.append(f"{name}: unknown version keys {sorted(extra)}")
        version = v.get("version", "")
        if not VERSION.match(version):
            problems.append(f"{name}: {version!r} isn't semver")
        if version in seen:
            problems.append(f"{name}: {version} is listed twice")
        seen.add(version)
        if not COMMIT.match(v.get("commit", "")):
            problems.append(f"{name} {version}: commit must be a full 40-character SHA")
    return problems


def validate(base):
    all_entries = entries()
    problems = []
    for name, entry in all_entries.items():
        problems += check_entry(name, entry)
    new = []
    if base:
        for name, entry in all_entries.items():
            old = git_show(base, f"plugins/{name}.toml")
            old_versions = {}
            if old is not None:
                old_entry = tomllib.loads(old)
                old_versions = {v["version"]: v for v in old_entry.get("versions", [])}
                if old_entry.get("repository") != entry.get("repository") or old_entry.get(
                    "path", ""
                ) != entry.get("path", ""):
                    problems.append(f"{name}: repository and path can't change; add a new plugin instead")
            versions = {v["version"]: v for v in entry.get("versions", [])}
            for version, old_v in old_versions.items():
                v = versions.get(version)
                if v is None:
                    problems.append(f"{name} {version}: a published version can't be removed; yank it")
                elif v.get("commit") != old_v.get("commit"):
                    problems.append(f"{name} {version}: a published version's commit can't change")
            new += [{"name": name, "version": v} for v in versions if v not in old_versions]
        for path in git_ls(base, "plugins"):
            if Path(path).stem not in all_entries:
                problems.append(f"{Path(path).stem}: an entry can't be removed; block it instead")
    if problems:
        fail("\n  ".join(["the entries have problems:"] + problems))
    if base:
        print(json.dumps(new))


def git_show(ref, path):
    out = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=ROOT, capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else None


def git_ls(ref, path):
    out = subprocess.run(
        ["git", "ls-tree", "--name-only", ref, f"{path}/"], cwd=ROOT, capture_output=True, text=True
    )
    return [l for l in out.stdout.splitlines() if l.endswith(".toml")]


def pending(records):
    records = Path(records)
    todo = [
        {"name": name, "version": v["version"]}
        for name, entry in entries().items()
        for v in entry.get("versions", [])
        if not (records / name / f"{v['version']}.json").exists()
    ]
    print(json.dumps(todo))


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def check_dependencies(plugin_dir):
    """Refuses git dependencies; path ones must stay in the clone."""
    cargo = plugin_dir / "Cargo.toml"
    if not cargo.exists():
        return
    if not (plugin_dir / "Cargo.lock").exists():
        fail("Cargo.lock is missing: commit it, so the build is the one you tested")
    with open(cargo, "rb") as f:
        manifest = tomllib.load(f)
    tables = [manifest.get("dependencies", {}), manifest.get("build-dependencies", {})]
    for target in manifest.get("target", {}).values():
        tables += [target.get("dependencies", {}), target.get("build-dependencies", {})]
    for table in tables:
        for dep, spec in table.items():
            if isinstance(spec, dict) and "git" in spec:
                fail(f"{dep} is a git dependency; depend on a crates.io release instead")


def build(name, version, out):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    entry = entries().get(name) or fail(f"no entry for {name}")
    v = next((v for v in entry.get("versions", []) if v["version"] == version), None)
    v or fail(f"{name} has no version {version}")
    # Always the same folder: builds of grammars' C code aren't the same
    # bytes from different paths, even with them remapped.
    src = Path(os.environ.get("REGISTRY_SRC", "/build/src"))
    if src.exists():
        shutil.rmtree(src)
    src.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "init", "-q", str(src)])
    run(["git", "-C", str(src), "fetch", "-q", "--depth", "1", entry["repository"], v["commit"]])
    run(["git", "-C", str(src), "checkout", "-q", "FETCH_HEAD"])
    epoch = subprocess.run(
        ["git", "-C", str(src), "log", "-1", "--format=%ct"], capture_output=True, text=True, check=True
    ).stdout.strip()
    plugin_dir = (src / entry.get("path", "")).resolve()
    if not plugin_dir.is_relative_to(src.resolve()):
        fail("path leaves the repository")
    with open(plugin_dir / "plugin.toml", "rb") as f:
        manifest = tomllib.load(f)
    if manifest.get("name") != name or manifest.get("version") != version:
        fail(
            f"plugin.toml at {v['commit'][:12]} is {manifest.get('name')} {manifest.get('version')}, "
            f"not {name} {version}"
        )
    check_dependencies(plugin_dir)
    env = dict(os.environ, SOURCE_DATE_EPOCH=epoch)
    cargo_home = os.environ.get("CARGO_HOME", str(Path.home() / ".cargo"))
    rustup_home = os.environ.get("RUSTUP_HOME", str(Path.home() / ".rustup"))
    env["RUSTFLAGS"] = (
        f"--remap-path-prefix={src}=/build --remap-path-prefix={cargo_home}=/cargo "
        f"--remap-path-prefix={rustup_home}=/rustup"
    )
    if (plugin_dir / "Cargo.toml").exists():
        run(["cargo", "build", "--locked", "--release", "--quiet"], cwd=plugin_dir, env=env)
    run(["merlin", "plugin", "pack", str(plugin_dir), "--out", str(out)], env=env)
    package = out / f"{name}-{version}.merlin"
    data = package.read_bytes()
    record = {
        "name": name,
        "version": version,
        "api": manifest["api"],
        "commit": v["commit"],
        "published": utc(datetime.now(timezone.utc)),
        "url": f"https://github.com/{REGISTRY_REPO}/releases/download/{name}-v{version}/{package.name}",
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "permissions": manifest.get("permissions", {}),
        "depends": manifest.get("depends", []),
        "manifest": {k: manifest[k] for k in SHOWN if k in manifest},
    }
    (out / "record.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(f"{package.name}: {len(data)} bytes, sha256 {record['sha256']}")


def version_key(version):
    core, _, pre = version.split("+")[0].partition("-")
    return (tuple(int(n) for n in core.split(".")), pre == "", pre)


def index(records, old, out):
    records = Path(records)
    serial = 0
    if old and Path(old).exists():
        serial = json.loads(Path(old).read_text()).get("serial", 0)
    now = datetime.now(timezone.utc)
    plugins = {}
    for name, entry in entries().items():
        versions = []
        newest_shown = {}
        for v in entry.get("versions", []):
            path = records / name / f"{v['version']}.json"
            if not path.exists():
                continue
            record = json.loads(path.read_text())
            versions.append(
                {
                    "version": v["version"],
                    "api": record["api"],
                    "commit": record["commit"],
                    "published": record["published"],
                    "url": record["url"],
                    "sha256": record["sha256"],
                    "size": record["size"],
                    "permissions": record["permissions"],
                    "depends": record["depends"],
                    "yanked": v.get("yanked"),
                    "blocked": v.get("blocked"),
                }
            )
            if not newest_shown or version_key(v["version"]) > version_key(newest_shown["_v"]):
                newest_shown = dict(record["manifest"], _v=v["version"])
        if not versions:
            continue
        newest_shown.pop("_v")
        plugins[name] = {
            "title": newest_shown.get("title", name),
            "description": newest_shown.get("description"),
            "badge": newest_shown.get("badge"),
            "hue": newest_shown.get("hue"),
            "license": newest_shown.get("license"),
            "repository": entry["repository"],
            "path": entry.get("path", ""),
            "owners": entry["owners"],
            "blocked": entry.get("blocked"),
            "versions": sorted(versions, key=lambda x: version_key(x["version"])),
        }
    doc = {
        "schema": 1,
        "serial": serial + 1,
        "generated": utc(now),
        "expires": utc(now + EXPIRY),
        "plugins": plugins,
    }
    Path(out).write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    print(f"index.json: serial {serial + 1}, {len(plugins)} plugins, expires {doc['expires']}")


# Programs that run anything they're given, which a reviewer must sign off.
RUN_ANYTHING = {"sh", "bash", "zsh", "fish", "dash", "python", "python3", "node", "deno", "bun",
                "ruby", "perl", "php", "lua", "cargo", "make", "cmake", "npm", "npx", "pip",
                "env", "sudo", "osascript", "powershell", "pwsh", "cmd"}


def summary(record_path):
    r = json.loads(Path(record_path).read_text())
    p = r["permissions"]
    lines = [f"### {r['name']} {r['version']}", "",
             f"{r['size']:,} bytes, sha256 `{r['sha256']}`, plugin API {r['api']}", ""]
    asks = []
    for key, words in [("editor-read", "read the open file"), ("editor-write", "change the open file"),
                       ("workspace-read", "read the project's files")]:
        if p.get(key):
            asks.append(words)
    outside = []
    if p.get("terminal"):
        outside.append("run command lines in a terminal")
    for prog in p.get("processes", []):
        flag = " (**runs anything it's given: needs a maintainer's sign-off**)" if prog in RUN_ANYTHING else ""
        outside.append(f"run `{prog}`{flag}")
    if p.get("debugger"):
        outside.append("start and drive debuggers")
    tier = "outside the sandbox" if outside else ("sandboxed" if asks else "data or nothing asked")
    lines.append(f"Review tier: **{tier}**")
    lines += [f"- {a}" for a in asks] + [f"- ⚠️ {o}" for o in outside] + [""]
    print("\n".join(lines))


def main(argv):
    match argv:
        case ["validate"]:
            validate(None)
        case ["validate", "--base", base]:
            validate(base)
        case ["pending", records]:
            pending(records)
        case ["build", name, version, out]:
            build(name, version, out)
        case ["index", records, old, out]:
            index(records, old, out)
        case ["summary", record]:
            summary(record)
        case _:
            print(__doc__, file=sys.stderr)
            sys.exit(2)


if __name__ == "__main__":
    main(sys.argv[1:])
