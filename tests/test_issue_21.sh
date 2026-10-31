#!/usr/bin/env bash
# Regression coverage for issue #21: booleans are not numeric in EigenScript.
set -euo pipefail

EIGS="${EIGENSCRIPT:-eigenscript}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Audit every tracked EigenScript and documentation occurrence of the boolean
# builtins used by this repository. A numeric comparison is invalid on v0.48.0.
if git -C "$ROOT" grep -n -E '(has_key|starts_with)[^#]*(==|!=)[[:space:]]*[01]' -- '*.eigs' '*.md' '*.sh'; then
    echo "FAIL: boolean-returning builtin is compared with 1 or 0"
    exit 1
fi
echo "PASS: boolean-returning builtin inventory has no numeric comparisons"

VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$ROOT/eigs.json")"
if ! grep -Fq "VERSION is \"$VERSION\"" "$ROOT/edit.eigs" ||
   ! grep -Fq "InauguralSystems/eigen-edit v$VERSION" "$ROOT/README.md"; then
    echo "FAIL: manifest, library, and documented release tag disagree"
    exit 1
fi
echo "PASS: manifest, library, and documented release tag all name v$VERSION"

# Stage the checkout exactly as an installed package, then exercise both a
# missing shift key (has_key false) and a present one (has_key true).
mkdir -p "$TMP/eigs_modules/edit"
cp "$ROOT/edit.eigs" "$ROOT/eigs.json" "$TMP/eigs_modules/edit/"
cat >"$TMP/consumer.eigs" <<'EOF'
import edit
doc is edit.new_doc of null
edit.replay of [doc, [{"key":"h","shift":true},{"key":"i"}]]
print of (edit.to_text of doc)
EOF
OUT="$(cd "$TMP" && "$EIGS" consumer.eigs)"
if [ "$OUT" != "Hi" ]; then
    echo "FAIL: installed-package example printed '$OUT', expected 'Hi'"
    exit 1
fi
echo "PASS: installed-package example prints Hi on the pinned runtime"

cat >"$TMP/observer.eigs" <<'EOF'
value is 1
print of (report of value)
EOF
OUT="$(cd "$TMP" && "$EIGS" observer.eigs)"
if [ "$OUT" != "equilibrium" ]; then
    echo "FAIL: observer example printed '$OUT', expected 'equilibrium'"
    exit 1
fi
echo "PASS: one-line observer example prints its documented equilibrium"
