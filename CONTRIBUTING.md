# Adding or updating a plugin

## A new plugin

1. Put the plugin's source in a public git repository. Its `plugin.toml`
   needs a `version`, and a `license` is expected. Commit `Cargo.lock`. Depend
   on the SDK from crates.io (`merlin-plugin`, `merlin-lsp`, `merlin-grammar`),
   not by `git` or a path outside your repository.
2. Check that it packs: `merlin plugin pack` in its folder.
3. Open a pull request adding `plugins/<name>.toml`:

   ```toml
   repository = "https://github.com/you/merlin-thing"
   path = ""                      # the folder holding plugin.toml; "" for the root
   owners = ["your-github-login"] # who may open PRs for new versions

   [[versions]]
   version = "0.1.0"              # must equal plugin.toml's version at that commit
   commit = "<the full 40-character SHA>"
   ```

The name must be 2 to 40 lowercase letters, digits and `-`, starting with a
letter. Names starting `merlin-` are for Merlin's own plugins.

## A new version

Add a `[[versions]]` table with the new version and commit. Published
versions never change: never edit or remove one. To withdraw one, add
`yanked = "why"` to it. Merlin won't offer it for new installs, and warns
anyone who has it.

## What Check does

Check validates the entries and builds each new version twice, from scratch,
in the registry's container. Both builds must give the same bytes. Its job
summary lists what the plugin asks to do.

## Review

How much review a plugin gets depends on what it may do:

| Asks for | A new plugin | An update from an owner |
|---|---|---|
| Nothing (themes, icons, layouts) | a maintainer merges once Check passes | merged once Check passes |
| `editor-read`, `editor-write`, `workspace-read` | a maintainer checks it does what it says | merged once Check passes, if its permissions didn't grow |
| `processes`, `terminal`, `debugger` | a written reason for each, and a maintainer reads the code that uses them | the same, if its permissions grew |

A program in `processes` runs with any arguments the plugin likes. So a
shell, interpreter or build tool (`sh`, `python`, `node`, `cargo` and so on)
lets a plugin run anything, and always needs a maintainer's sign-off. Check
points these out.

Maintainers can add `blocked = "why"` to a version or a whole entry for a
plugin that's malicious or dangerous. Merlin turns a blocked plugin off.
