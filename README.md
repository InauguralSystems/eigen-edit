# eigen-edit

A small text editor written in [EigenScript](https://github.com/InauguralSystems/EigenScript).

It exists **as its own thing** — clone it and run it on your desktop — and
it is also the editor [EigenOS](https://github.com/InauguralSystems/EigenOS)
imports for its desktop shell. Same `edit.eigs`, three surfaces: an X11
window on Linux, the WASM playground, and the EigenOS framebuffer. The app
does not belong to the OS; the OS is one of its consumers.

![eigen-edit rendering two lines with a caret](docs/screenshot.png)

## Run it standalone

```sh
# one-time: build a gfx-capable EigenScript
git clone https://github.com/InauguralSystems/EigenScript.git
make -C EigenScript gfx        # dlopens system SDL2 at runtime; no -dev headers needed

# then, in this repo:
EigenScript/src/eigenscript main.eigs
```

Type to insert. **Arrows / Home / End** move the caret, **Backspace / Delete**
erase (Backspace at column 0 merges into the line above), **Enter** splits a
line, **Escape** or the window close box quits.

## Why it's shaped this way

The interesting part of a text editor is the buffer model, and here it is
**pure EigenScript with no graphics dependency** — `edit.eigs` exports
`new_doc`, `insert_str`, `newline`, `backspace`, `delete_fwd`, `move`,
`apply_key`, `replay`, and `to_text`, and defines `run` (the gfx front-end)
without calling it. So `import edit` is side-effect-free and the whole editor
is testable headlessly.

Input is a **deterministic replay tape.** A gfx keydown event carries a
scancode name (`"a"`, `"1"`, `"space"`, `"return"`) plus a `shift` flag —
there is no text field, so the editor owns the key→character mapping. That
means any editing session is a list of `{key, shift}` events, and replaying
that list reconstructs the buffer **byte-for-byte**. The smoke test drives
tapes through the core and byte-diffs `to_text` against known output — no
window, no xvfb, fully deterministic:

```sh
EIGENSCRIPT=/path/to/eigenscript bash tests/test_smoke.sh
```

## Two oracles, because it has a UI

A byte-diff of the buffer model is necessary but not sufficient — it never
looks at what a user sees. So correctness is checked on two **independent**
paths that must agree:

1. **Model** — `tests/test_smoke.sh` replays tapes and byte-diffs `to_text`
   against expected output. Catches buffer-logic bugs. Headless, no display.
2. **Render** — `tests/ui_oracle.py` renders through the real `draw_frame`
   into a window, screenshots it, and **decodes the pixels back into text**,
   asserting they equal the headless model. Catches rendering bugs: a dropped
   line, a caret that paints over a glyph, a wrong character. The decode is
   exact, not fuzzy OCR — the bitmap font (forced on via a nonexistent
   `EIGS_GFX_FONT`) is a fixed atlas on a deterministic 12×14 px cell grid,
   so the model *is* the reference; no self-authored golden image.

The render oracle validates itself: a deliberately broken `draw_frame` (drops
the first line) is run through the same pipeline and must be caught. It runs
in CI under `xvfb` against a gfx build, and already paid for itself by finding
a caret that nibbled the glyph under the cursor.

```sh
# needs the gfx build + xvfb + xdotool + PIL
xvfb-run -a python3 tests/ui_oracle.py
```

## Use it as a library

The buffer core is a normal EigenScript package:

```sh
eigenscript --pkg add InauguralSystems/edit https://github.com/InauguralSystems/eigen-edit v0.1.0
```

```eigenscript
import edit
doc is edit.new_doc of null
edit.replay of [doc, [{"key":"h","shift":1},{"key":"i"}]]
print of (edit.to_text of doc)      # -> Hi
```

## Layout

```
.
├── eigs.json          # package manifest (name: edit)
├── edit.eigs          # importable buffer core + the gfx `run` front-end
├── main.eigs          # standalone launcher: import edit; edit.run of null
├── tests/
│   ├── test_smoke.sh  # model oracle (headless buffer byte-diff)
│   └── ui_oracle.py   # render oracle (pixels decoded back to model)
└── .github/workflows/test.yml   # both oracles as CI jobs
```

CI runs two jobs: `test` builds a plain (non-gfx) EigenScript and runs the
model smoke test; `ui-oracle` builds the gfx EigenScript and runs the
render-vs-model check under `xvfb`.

## License

MIT — see [LICENSE](LICENSE).
