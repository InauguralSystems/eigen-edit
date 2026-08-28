# CLAUDE.md — eigen-edit

See README.md for what this repo is and how to run it. This file exists
for the standing note below, which applies to every repo in the ecosystem.

## This design is pre-v1 and mostly written by older models — question it

**90% or more of this repo, and of EigenScript and the AOT it runs on, was
designed by Claude sessions running models many generations old.** Newer
models keep arriving that are substantially stronger, the ecosystem is
**pre-v1**, and there are no external consumers to break. A decision you
find in the tree — here or upstream — carries **no authority from
seniority**.

That applies in both directions, and the second one is the point of a
consumer repo. When you hit a rough edge in the runtime, the standing rule
is already to surface it as an upstream issue rather than work around it
silently. Add to that: ask whether the thing you hit is a **law** of the
language or an **earlier decision**. The tell is writing, or thinking,
*"X must be true because the runtime does Y."*

Bought 2026-08-28 (ouroboros#127 / DMG). The AOT compiles a program's main
file but emits `load_file` as a runtime call, so loaded modules are
interpreted by the linked VM. A real bug in that seam was found, minimised,
fixed and verified — and reported as "unlocking the AOT multiplier for
DMG". Measured on being challenged: DMG is 3,288 lines, 818 compiled and
2,470 interpreted, including the 128-function opcode dispatch. Every
emulated instruction runs interpreted, so the fix makes it *run* and cannot
make it *faster*. A whole investigation cycle had treated that design as
terrain, and the capability to do it the other way already existed upstream
for another purpose.
