#!/usr/bin/env bash
# Smoke test for eigen-edit.
#
# Strategy: the editor's buffer core is pure and gfx-free, and input is a
# deterministic replay tape (a list of {key, shift} events — exactly what
# the gfx front-end feeds it). So we stage the package the way a consumer
# would, replay a scripted tape onto a fresh document, and byte-diff the
# resulting buffer text against a known-good expectation. No window, no
# xvfb — the same key sequence reconstructs the same bytes every time.
set -euo pipefail

EIGS="${EIGENSCRIPT:-eigenscript}"
PKG_NAME="$(python3 -c 'import json;print(json.load(open("eigs.json"))["name"])')"
PKG_ROOT="$(pwd)"

TMP="$(mktemp -d)"
trap "rm -rf '$TMP'" EXIT

# Stage the package as a consumer's vendored dependency.
mkdir -p "$TMP/eigs_modules/$PKG_NAME"
cp -a "$PKG_ROOT/$PKG_NAME.eigs" "$TMP/eigs_modules/$PKG_NAME/"
cp -a "$PKG_ROOT/eigs.json" "$TMP/eigs_modules/$PKG_NAME/"

# Consumer program: replay several tapes, print each buffer between
# BEGIN/END sentinels so multi-line results diff unambiguously.
cat > "$TMP/app.eigs" <<EOF
import $PKG_NAME

define run_case(name, script) as:
    local d is $PKG_NAME.new_doc of null
    $PKG_NAME.replay of [d, script]
    print of ("BEGIN " + name)
    print of ($PKG_NAME.to_text of d)
    print of ("END " + name)

# "Hello" with a capital H, newline, "world!" (shifted 1 -> !)
run_case of ["typing", [{"key":"h","shift":1},{"key":"e"},{"key":"l"},{"key":"l"},{"key":"o"},{"key":"return"},{"key":"w"},{"key":"o"},{"key":"r"},{"key":"l"},{"key":"d"},{"key":"1","shift":1}]]

# backspace across a line boundary merges lines: "ab" + Enter + backspace
run_case of ["merge", [{"key":"a"},{"key":"b"},{"key":"return"},{"key":"backspace"}]]

# arrow navigation then insert: "abc", left, left, "X" -> "aXbc"
run_case of ["navigate", [{"key":"a"},{"key":"b"},{"key":"c"},{"key":"left"},{"key":"left"},{"key":"x","shift":1}]]

# forward delete from line start: "abc", home, delete -> "bc"
run_case of ["delete", [{"key":"a"},{"key":"b"},{"key":"c"},{"key":"home"},{"key":"delete"}]]

# number row with shift produces symbols
run_case of ["symbols", [{"key":"2","shift":1},{"key":"3","shift":1},{"key":"4","shift":1}]]
EOF

cd "$TMP"
OUT="$("$EIGS" app.eigs 2>&1)"

EXPECT="$(cat <<'EOF'
BEGIN typing
Hello
world!
END typing
BEGIN merge
ab
END merge
BEGIN navigate
aXbc
END navigate
BEGIN delete
bc
END delete
BEGIN symbols
@#$
END symbols
EOF
)"

if [ "$OUT" != "$EXPECT" ]; then
    echo "FAIL: replayed buffer did not match expectation"
    echo "--- got ---";      printf '%s\n' "$OUT"
    echo "--- expected ---"; printf '%s\n' "$EXPECT"
    diff <(printf '%s\n' "$EXPECT") <(printf '%s\n' "$OUT") || true
    exit 1
fi
echo "PASS: eigen-edit buffer core replays byte-exact across 5 tapes"

# The importable surface must not leak private helpers (leading _).
cat > "$TMP/keys.eigs" <<EOF
import $PKG_NAME
ks is keys of $PKG_NAME
for i in range of (len of ks):
    if (starts_with of [ks[i], "_"]) == 1:
        print of ("LEAKED " + ks[i])
print of "keys-checked"
EOF
OUT2="$("$EIGS" "$TMP/keys.eigs" 2>&1)"
if echo "$OUT2" | grep -q "LEAKED"; then
    echo "FAIL: private (_-prefixed) names are visible to importers"
    echo "$OUT2"
    exit 1
fi
echo "PASS: private helpers stay out of the import surface"
