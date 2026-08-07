#!/usr/bin/env bash
# Packages broadcastExtension/ for the Chrome Web Store.
#
# The store requires manifest.json at the *root* of the archive, so we zip from
# inside the extension directory — zipping `broadcastExtension/` from the repo
# root nests everything one level down and the upload is rejected with
# "manifest file is missing or unreadable".
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$repo_root/broadcastExtension"
out="$repo_root/broadcast-extension.zip"

version="$(grep -o '"version"[[:space:]]*:[[:space:]]*"[^"]*"' "$src/manifest.json" | head -1 | sed 's/.*"\([^"]*\)"$/\1/')"

# Stage a copy so the dev-only localhost/127.0.0.1 host_permissions entries
# (kept in the checked-in manifest.json so local testing works out of the box
# — see README) never reach the store, without needing a manual edit/revert
# of the source manifest before/after packaging.
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
cp -R "$src/." "$stage/"

python3 - "$stage/manifest.json" <<'PY'
import json, sys

path = sys.argv[1]
with open(path) as f:
    manifest = json.load(f)

before = manifest.get("host_permissions", [])
after = [h for h in before if "localhost" not in h and "127.0.0.1" not in h]
removed = [h for h in before if h not in after]
manifest["host_permissions"] = after

with open(path, "w") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")

if removed:
    print(f"Stripped dev host_permissions before packaging: {', '.join(removed)}")
PY

rm -f "$out"
cd "$stage"
zip -r "$out" . -x "*.DS_Store" "*/.DS_Store"

echo
echo "Packaged v$version → $out"
unzip -l "$out"
