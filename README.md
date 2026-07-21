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

## Three oracles

A byte-diff against my own expectations is a golden master — it pins
regressions but can't tell you what *right* looks like. So correctness rests
on three **independent** checks, each answering a different question:

1. **Model** (`tests/test_smoke.sh`) — replays tapes and byte-diffs `to_text`.
   *Self-consistency:* did the buffer logic change? Headless, no display.
2. **Differential vs a real editor** (`tests/diff_vs_editor.py`) — replays the
   *same* keystrokes through headless **vim** and byte-diffs its saved buffer.
   *External truth:* for the operations every real editor agrees on — typing,
   Enter, Backspace (including line-join), Tab — "what right looks like" isn't
   mine to invent; it's what a used editor actually does. vim's output is the
   reference. (Cursor navigation and forward-delete diverge across editors, so
   they're left to the other two oracles.)
3. **Render** (`tests/ui_oracle.py`) — because it's a UI, renders through the
   real `draw_frame`, screenshots the window, and **decodes the pixels back
   into text**, asserting they equal the model. *Render fidelity:* a dropped
   line, a caret painting over a glyph, a wrong character. Exact decode, not
   fuzzy OCR — the bitmap font (forced via a nonexistent `EIGS_GFX_FONT`) is a
   fixed atlas on a deterministic 12×14 px cell grid, and the render oracle
   validates itself: a deliberately broken `draw_frame` (drops line 0) must be
   caught. It already paid for itself by finding a caret that nibbled the
   glyph under the cursor.

```sh
EIGENSCRIPT=/path/to/eigenscript python3 tests/diff_vs_editor.py   # needs vim
xvfb-run -a python3 tests/ui_oracle.py                             # needs gfx build + xvfb + xdotool + PIL
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
│   ├── test_smoke.sh      # model oracle (headless buffer byte-diff)
│   ├── diff_vs_editor.py  # differential oracle vs headless vim
│   └── ui_oracle.py       # render oracle (pixels decoded back to model)
└── .github/workflows/test.yml   # all three oracles as CI steps/jobs
```

CI runs two jobs: `test` builds a plain (non-gfx) EigenScript and runs the
model smoke test **and** the vim differential oracle; `ui-oracle` builds the
gfx EigenScript and runs the render-vs-model check under `xvfb`.

## License

MIT — see [LICENSE](LICENSE).
