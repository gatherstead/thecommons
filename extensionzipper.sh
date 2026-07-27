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

# The zip is built as-is with no filtering, so a stray dev host left in
# host_permissions (see README) would ship to the store. Catch it here.
if sed -n '/"host_permissions"/,/]/p' "$src/manifest.json" | grep -q "localhost\|127.0.0.1"; then
  echo "ERROR: localhost entry in host_permissions — revert it before packaging." >&2
  exit 1
fi

rm -f "$out"
cd "$src"
zip -r "$out" . -x "*.DS_Store" "*/.DS_Store"

echo
echo "Packaged v$version → $out"
unzip -l "$out"
