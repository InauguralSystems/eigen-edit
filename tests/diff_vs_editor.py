#!/usr/bin/env python3
"""Differential oracle: eigen-edit vs a real, widely-used editor (vim).

The point of this file: for the operations every real editor agrees on —
typing, Enter, Backspace (including joining a line), Tab — "what right looks
like" is not something I get to invent. It's what a real editor actually does.
So we replay the SAME keystrokes through headless vim, save its buffer, and
byte-diff it against eigen-edit's `to_text`. vim's output IS the reference; no
hand-authored expectation.

vim's insert mode is modeless like eigen-edit, which makes the mapping direct.
We stay on the consensus subset only — cursor navigation (arrows/home/end) and
forward-delete diverge across editors and don't replay unambiguously in a vim
keystroke script, so those are left to the model + render oracles. Where a
behavior legitimately differs between editors, the choice is made deliberately
elsewhere and cited; it does not belong in this diff.

Two independent references meet here: the character a shifted key produces is
the US keyboard layout (encoded in KEYMAP below, independently of edit.eigs's
own table), and the editing result is vim's. A bug in eigen-edit's key mapping
OR its editing shows up as a diff against one or the other.
"""
import json, os, shutil, subprocess, sys, tempfile

EIGS = os.environ.get("EIGENSCRIPT", "eigenscript")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VIM = next((b for b in ("vim", "vim.tiny", "vi") if shutil.which(b)), None)

# US-layout character each (key, shift) yields — the ground truth a real
# keyboard hands to a terminal. Encoded here independently of edit.eigs.
_SHIFT_DIGIT = dict(zip("1234567890", "!@#$%^&*()"))
_SHIFT_PUNCT = {"-": "_", "=": "+", "[": "{", "]": "}", "\\": "|", ";": ":",
                "'": '"', ",": "<", ".": ">", "/": "?", "`": "~"}


def key_char(key, shift):
    """The printable char for (key, shift), or a control token, or None."""
    if key == "space":
        return " "
    if key == "tab":
        return "\t"
    if key == "return":
        return "\r"
    if key == "backspace":
        return "\b"
    if len(key) == 1 and key.isalpha():
        return key.upper() if shift else key
    if len(key) == 1:
        if shift:
            return _SHIFT_DIGIT.get(key) or _SHIFT_PUNCT.get(key, key)
        return key
    return None  # non-consensus key (arrow/delete/home/end) — not used here


def eigs_lit(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def eigs_model(tape):
    """eigen-edit's buffer after replaying the tape, as a list of lines."""
    events = "[" + ", ".join('{"key": %s, "shift": %d}' % (eigs_lit(k), sh)
                             for k, sh in tape) + "]"
    prog = ('import edit\n'
            'doc is edit.new_doc of null\n'
            'edit.replay of [doc, %s]\n'
            'print of (edit.to_text of doc)\n' % events)
    tmp = tempfile.mkdtemp()
    try:
        md = os.path.join(tmp, "eigs_modules", "edit"); os.makedirs(md)
        shutil.copy(os.path.join(REPO, "edit.eigs"), os.path.join(md, "edit.eigs"))
        shutil.copy(os.path.join(REPO, "eigs.json"), os.path.join(md, "eigs.json"))
        app = os.path.join(tmp, "app.eigs"); open(app, "w").write(prog)
        r = subprocess.run([EIGS, app], cwd=tmp, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise RuntimeError(r.stdout + r.stderr)
        return r.stdout.rstrip("\n").split("\n")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def vim_reference(tape):
    """The same keystrokes through headless vim; vim's saved buffer = truth."""
    keys = bytearray(b":set backspace=indent,eol,start expandtab softtabstop=4\r")
    keys += b"i"  # enter insert mode (modeless, like eigen-edit)
    for key, shift in tape:
        ch = key_char(key, shift)
        if ch is None:
            raise ValueError("non-consensus key in vim tape: %r" % key)
        keys += ch.encode()
    keys += b"\x1b:wq\r"  # leave insert, write
    tmp = tempfile.mkdtemp()
    try:
        script = os.path.join(tmp, "keys"); open(script, "wb").write(keys)
        target = os.path.join(tmp, "buf.txt"); open(target, "w").close()  # empty
        subprocess.run([VIM, "-u", "NONE", "-N", "-n", "-s", script, target],
                       capture_output=True, timeout=60)
        text = open(target).read()
        return text.rstrip("\n").split("\n") if text else [""]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# Consensus-only tapes: type / Enter / Backspace / Tab.
CASES = [
    ("typing",   [("h",1),("i",0),("return",0),("w",0),("o",0),("r",0),("l",0),("d",0),("1",1)]),
    ("caps",     [("t",1),("h",1),("e",0),("space",0),("c",1),("a",0),("t",0)]),
    ("symbols",  [("2",1),("3",1),("4",1),("5",1),("6",1),("7",1)]),
    ("punct",    [("a",0),("=",1),("b",0),("/",1),("[",1)]),
    ("bkspc",    [("c",0),("a",0),("t",0),("s",0),("backspace",0)]),
    ("join",     [("a",0),("b",0),("return",0),("backspace",0)]),
    ("join2",    [("f",0),("o",0),("o",0),("return",0),("b",0),("backspace",0),("backspace",0)]),
    ("tab",      [("tab",0),("x",0),("y",0)]),
    ("multiline",[("o",0),("n",0),("e",0),("return",0),("t",0),("w",0),("o",0),("return",0),("t",0),("h",0),("r",0),("e",0),("e",0)]),
]


def main():
    if not VIM:
        print("SKIP: no vim/vi found — differential-vs-editor oracle needs one")
        sys.exit(2)
    print("reference editor: %s" % VIM)
    failures = 0
    for name, tape in CASES:
        mine = eigs_model(tape)
        ref = vim_reference(tape)
        if mine == ref:
            print("PASS %-9s eigen-edit == vim: %r" % (name, ref))
        else:
            failures += 1
            print("FAIL %-9s\n   eigen-edit: %r\n   vim (ref) : %r" % (name, mine, ref))
    if failures:
        print("\n%d divergence(s) from the reference editor" % failures)
        sys.exit(1)
    print("\neigen-edit matches vim on every consensus operation")


if __name__ == "__main__":
    main()
