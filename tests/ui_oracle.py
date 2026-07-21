#!/usr/bin/env python3
"""UI oracle for eigen-edit: the rendered pixels must decode back to the model.

An editor is a UI app, so a byte-diff of the buffer model (test_smoke.sh) is
not enough — it never looks at what a user sees. This oracle closes that gap
with two INDEPENDENT paths that must agree:

  model  = eigenscript runs edit.replay(tape) then prints to_text(doc)
  render = eigenscript runs edit.draw_frame(doc) into a real window; we
           screenshot it and DECODE the pixels back into text.

The decode is exact, not fuzzy OCR: EigenScript's 5x7 bitmap font (forced on
via a nonexistent EIGS_GFX_FONT) is a fixed glyph atlas, and draw_frame lays
text out on a deterministic 12x14 px cell grid from origin (8,8). We build the
atlas once by rendering the printable charset, then read each editor cell and
match its lit-pixel signature. If the render drops a line, shifts the caret
into a glyph, or paints the wrong character, the decoded text diverges from
the model and this oracle fails.

The checker is itself validated: a deliberately broken draw_frame (drops the
first line) is run through the same pipeline and MUST be caught.

Assumes an X display is present (CI wraps this in `xvfb-run`). Requires the
gfx build of eigenscript (EIGENSCRIPT env var) plus xdotool, xwd, PIL.
"""
import os, subprocess, sys, tempfile, time, struct, shutil
from PIL import Image

EIGS = os.environ.get("EIGENSCRIPT", "eigenscript")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = dict(os.environ, SDL_VIDEODRIVER="x11",
           EIGS_GFX_FONT="/nonexistent/force-bitmap.ttf")  # deterministic bitmap font

CELL_W, CELL_H, ORIGIN_X, ORIGIN_Y = 12, 14, 8, 8   # scale-2 bitmap-font grid
INK = lambda r, g, b: min(r, g, b) > 150             # grey text; excludes caret+bg
# Printable charset minus space (space renders blank = an empty cell).
CHARSET = "".join(chr(c) for c in range(33, 127))


def eigs_str(s):
    """EigenScript string literal for s."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def eigs_tape(tape):
    """[(keyname, shift), ...] -> EigenScript event-list literal."""
    return "[" + ", ".join('{"key": %s, "shift": %d}' % (eigs_str(k), sh)
                           for k, sh in tape) + "]"


def run_model(edit_path, tape):
    """Headless: replay the tape and print the buffer text (the reference)."""
    prog = ('import edit\n'
            'doc is edit.new_doc of null\n'
            'edit.replay of [doc, %s]\n'
            'print of (edit.to_text of doc)\n' % eigs_tape(tape))
    return _run_prog(edit_path, prog).rstrip("\n").split("\n")


def _run_prog(edit_path, prog):
    """Stage edit_path as a package and run a consumer program, return stdout."""
    tmp = tempfile.mkdtemp()
    try:
        moddir = os.path.join(tmp, "eigs_modules", "edit")
        os.makedirs(moddir)
        shutil.copy(edit_path, os.path.join(moddir, "edit.eigs"))
        shutil.copy(os.path.join(REPO, "eigs.json"), os.path.join(moddir, "eigs.json"))
        app = os.path.join(tmp, "app.eigs")
        open(app, "w").write(prog)
        out = subprocess.run([EIGS, app], cwd=tmp, env=ENV,
                             capture_output=True, text=True, timeout=60)
        if out.returncode != 0:
            raise RuntimeError("eigs failed: " + out.stdout + out.stderr)
        return out.stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _capture(edit_path, render_body, title, w=720, h=480):
    """Run a render program in a window, screenshot it, return a PIL image."""
    tmp = tempfile.mkdtemp()
    try:
        moddir = os.path.join(tmp, "eigs_modules", "edit")
        os.makedirs(moddir)
        shutil.copy(edit_path, os.path.join(moddir, "edit.eigs"))
        shutil.copy(os.path.join(REPO, "eigs.json"), os.path.join(moddir, "eigs.json"))
        app = os.path.join(tmp, "r.eigs")
        prog = ('import edit\n%s\n'
                'ok is gfx_open of [%d, %d, %s]\n'
                'n is 0\n'
                'loop while n < 600:\n'
                '    %s\n'
                '    gfx_present of null\n'
                '    gfx_delay of 16\n'
                '    n is n + 1\n'
                'gfx_close of null\n'
                % (render_body["setup"], w, h, eigs_str(title), render_body["frame"]))
        open(app, "w").write(prog)
        proc = subprocess.Popen([EIGS, app], cwd=tmp, env=ENV,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            wid = None
            for _ in range(50):
                time.sleep(0.1)
                r = subprocess.run(["xdotool", "search", "--name", title],
                                   env=ENV, capture_output=True, text=True)
                if r.stdout.strip():
                    wid = r.stdout.strip().split("\n")[0]
                    break
            if not wid:
                raise RuntimeError("window never appeared: " + (proc.stdout.read() or ""))
            time.sleep(0.3)
            xwd = os.path.join(tmp, "s.xwd")
            subprocess.run(["xwd", "-id", wid, "-out", xwd], env=ENV, check=True,
                           capture_output=True)
            return _xwd_to_image(xwd)
        finally:
            proc.terminate()
            try: proc.wait(timeout=5)
            except Exception: proc.kill()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _xwd_to_image(path):
    d = open(path, "rb").read()
    f = struct.unpack(">25I", d[:100])
    hs, pw, ph, bpl, ncolors = f[0], f[4], f[5], f[12], f[19]
    off = hs + ncolors * 12
    img = Image.new("RGB", (pw, ph))
    px = img.load()
    for y in range(ph):
        row = off + y * bpl
        for x in range(pw):
            p = struct.unpack_from("<I", d, row + x * 4)[0]
            px[x, y] = ((p >> 16) & 255, (p >> 8) & 255, p & 255)
    return img


def _cell_sig(px, cx, cy):
    """Lit-pixel signature of the 12x14 cell whose top-left is (cx, cy)."""
    sig = frozenset((dx, dy) for dy in range(CELL_H) for dx in range(CELL_W)
                    if INK(*px[cx + dx, cy + dy]))
    return sig


def build_atlas(edit_path):
    """char -> lit-pixel signature, rendered through the same font/scale."""
    body = {"setup": "", "frame": "gfx_clear of [24,24,30]\n    gfx_text of [8, 8, %s, 220,220,230, 2]"
            % eigs_str(CHARSET)}
    img = _capture(edit_path, body, "eigen-edit-atlas", w=CELL_W * len(CHARSET) + 40, h=40)
    px = img.load()
    atlas = {}
    for k, ch in enumerate(CHARSET):
        sig = _cell_sig(px, ORIGIN_X + k * CELL_W, ORIGIN_Y)
        atlas[sig] = ch
    atlas[frozenset()] = " "   # empty cell decodes to space
    return atlas


def decode(img, atlas, nrows=6, ncols=58):
    """Decode the editor screenshot into text lines via the atlas."""
    px = img.load()
    W, H = img.size
    lines = []
    for i in range(nrows):
        cy = ORIGIN_Y + i * CELL_H
        if cy + CELL_H > H:
            break
        chars = []
        for c in range(ncols):
            cx = ORIGIN_X + c * CELL_W
            if cx + CELL_W > W:
                break
            sig = _cell_sig(px, cx, cy)
            chars.append(atlas.get(sig, "�"))   # unknown glyph -> replacement char
        lines.append("".join(chars).rstrip())
    # trim trailing blank rows
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def render_lines(edit_path, tape, atlas):
    body = {"setup": ("doc is edit.new_doc of null\n"
                      "edit.replay of [doc, %s]" % eigs_tape(tape)),
            "frame": "edit.draw_frame of doc"}
    img = _capture(edit_path, body, "eigen-edit-oracle")
    return decode(img, atlas)


CASES = [
    ("typing",  [("h",1),("e",0),("l",0),("l",0),("o",0),("return",0),
                 ("w",0),("o",0),("r",0),("l",0),("d",0)]),
    ("symbols", [("2",1),("3",1),("4",1)]),
    ("merge",   [("a",0),("b",0),("return",0),("backspace",0)]),
    ("indent",  [("tab",0),("a",0),("b",0)]),
    ("edits",   [("c",0),("a",0),("t",0),("left",0),("left",0),("x",1)]),
]


def main():
    edit_path = os.path.join(REPO, "edit.eigs")
    atlas = build_atlas(edit_path)
    print("atlas: %d glyphs" % len(atlas))
    failures = 0
    for name, tape in CASES:
        model = run_model(edit_path, tape)
        shown = render_lines(edit_path, tape, atlas)
        if shown == model:
            print("PASS %-8s render decodes to model: %r" % (name, model))
        else:
            failures += 1
            print("FAIL %-8s\n   model : %r\n   screen: %r" % (name, model, shown))

    # --- validate the checker: a broken draw_frame MUST be caught ---
    broken = os.path.join(tempfile.mkdtemp(), "edit.eigs")
    src = open(edit_path).read().replace(
        "    for i in range of (len of doc.lines):\n"
        "        gfx_text of [pad, y, doc.lines[i], 220, 220, 230, 2]\n"
        "        y is y + lh",
        "    for i in range of (len of doc.lines):\n"
        "        if i > 0:\n"
        "            gfx_text of [pad, y, doc.lines[i], 220, 220, 230, 2]\n"
        "        y is y + lh")
    assert src != open(edit_path).read(), "planted-fault substitution did not apply"
    open(broken, "w").write(src)
    tape = CASES[0][1]  # the two-line 'typing' case
    model = run_model(broken, tape)
    shown = render_lines(broken, tape, atlas)
    if shown != model:
        print("PASS checker  broken render (drops line 0) was caught: %r != %r" % (shown, model))
    else:
        failures += 1
        print("FAIL checker  planted render bug slipped through — oracle is blind")

    if failures:
        print("\n%d UI-oracle failure(s)" % failures)
        sys.exit(1)
    print("\nall UI-oracle checks passed")


if __name__ == "__main__":
    main()
