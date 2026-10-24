# Tap patches

`Formula/omlx.rb` installs an upstream release tarball and applies these
patches to it, so every patch here must apply to the tag the formula pins.

- `power-states.patch` — per-state power policies (AC, battery, sealed lid)
  for the server and the dashboard.
- `clef-context-window.patch` — Clef serves the backbone's context window
  instead of the hardcoded 16384.
- `omlx-formula-downstream.patch` — the diff between the tag's
  `Formula/omlx.rb` and the tap's recipe. Keep the two in step.

## Moving the pin

1. Rebase each source patch onto the new tag and regenerate it from a tree
   that already has the earlier patches applied, in filename order.
2. Regenerate `omlx-formula-downstream.patch` from the new tag's recipe.
3. Set `url`, `sha256`, `version`, `revision` and each `patch do` sha256 in
   `Formula/omlx.rb`. A dev tag such as `v0.7.3.dev1` needs `version`
   spelled out, because Homebrew reads it as `1` otherwise. Bump `revision`
   only when the same version needs a second build.

## Verifying a pin

This fork runs no GitHub Actions. Check the patch set by hand before
pushing:

```sh
git clone --no-checkout https://github.com/jundot/omlx.git /tmp/omlx-check
git -C /tmp/omlx-check checkout -f v0.7.3.dev1
cp -R patches /tmp/omlx-check/patches
for p in /tmp/omlx-check/patches/*.patch; do
  git -C /tmp/omlx-check apply --3way --whitespace=nowarn "$p"
done
ruby -c Formula/omlx.rb
```

Then confirm both kinds of checksum: the recipe's `patch do` sha256s must
name the files in `patches/`, and the tarball sha256 must match the
release.

```sh
shasum -a 256 patches/*.patch
curl -sL https://github.com/jundot/omlx/archive/refs/tags/v0.7.3.dev1.tar.gz | shasum -a 256
```

## Upstream sync

The source tree here is the upstream tag with these patches applied. The
fork deletes upstream's `.github/workflows/` and `.github/dependabot.yml`:
they describe jundot/omlx's own CI, and in a tap they only produce failing
runs and mail. Delete them again after every sync.
