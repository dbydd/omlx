# Tap patches

`Formula/omlx.rb` installs an upstream source tarball and applies these
patches to it, so every patch here must apply to the commit the formula pins.

- `power-states.patch` — per-state power policies (AC, battery, sealed lid)
  for the server and the dashboard.
- `clef-context-window.patch` — Clef serves the backbone's context window
  instead of the hardcoded 16384.
- `ming3-tts-detection.patch` — Ming-3.0 TTS and Ming-omni-tts checkpoints
  declare `model_type: "dense"`, which the LLM-collision strip removes from
  the mlx-audio-derived TTS set, so model discovery classifies them as LLMs.
  The patch adds their architecture string to `AUDIO_TTS_ARCHITECTURES`.
- `omlx-formula-downstream.patch` — the diff between the pinned commit's
  `Formula/omlx.rb` and the tap's recipe. Keep the two in step.

## The pin

The formula pins upstream `main` at a commit, not a tag, because the pieces
this tap needs landed after the last release: `v0.7.3rc1` still pins
mlx-audio 0.5.7, and Ming-3.0 TTS needs 0.6.1 or newer (0.4.3–0.6.0 load the
checkpoint and speak the wrong words instead of failing). `main` at
`33f25891` carries mlx-audio 0.6.3 and the LFM3 speech engine.

`version` stays the last tag's number because the commit has no version of
its own; `revision` is what moves when the same upstream version gets a new
pin or a rebuilt patch set.

## Moving the pin

1. Rebase each source patch onto the new commit and regenerate it from a
   tree that already has the earlier patches applied, in filename order.
2. Regenerate `omlx-formula-downstream.patch` from the pinned commit's
   recipe.
3. Set `url`, `sha256`, `version`, `revision` and each `patch do` sha256 in
   `Formula/omlx.rb`. A dev tag such as `v0.7.3.dev1` needs `version`
   spelled out, because Homebrew reads it as `1` otherwise. Bump `revision`
   only when the same version needs another build.

## Verifying a pin

This fork runs no GitHub Actions. Check the patch set by hand before
pushing:

```sh
git clone --no-checkout https://github.com/jundot/omlx.git /tmp/omlx-check
git -C /tmp/omlx-check checkout -f 33f2589102e7f778b23cf2a2ece16716396dfb85
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
curl -sL https://github.com/jundot/omlx/archive/33f2589102e7f778b23cf2a2ece16716396dfb85.tar.gz | shasum -a 256
```

Ming-3.0 detection is one call. With mlx-audio 0.6.3 or newer installed:

```sh
python -c "from pathlib import Path; from omlx.model_discovery import detect_model_type; \
print(detect_model_type(Path('$HOME/.omlx/models/Ming-3.0-tts-0.5B-bf16')))"
```

It must print `audio_tts`. Before the patch it prints `llm`.

## Upstream sync

The source tree here is the pinned commit with these patches applied. The
fork deletes upstream's `.github/workflows/` and `.github/dependabot.yml`:
they describe jundot/omlx's own CI, and in a tap they only produce failing
runs and mail. Delete them again after every sync.
