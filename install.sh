#!/usr/bin/env bash
# Copies mods/codex-limits into the Herdr app's mods folder.
# Usage: ./install.sh [--force]
set -euo pipefail

force=0
case "${1:-}" in
  "") ;;
  --force) force=1 ;;
  *) echo "usage: $0 [--force]" >&2; exit 2 ;;
esac

src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/mods/codex-limits"
mods="${HERDR_APP_HOME:-$HOME/.config/herdr-app}/mods"
dest="$mods/codex-limits"

if [ -e "$dest" ]; then
  if [ "$force" -ne 1 ]; then
    echo "$dest already exists; rerun with --force to replace it" >&2
    exit 1
  fi
  rm -rf -- "$dest"
fi

mkdir -p "$mods"
cp -R -- "$src" "$dest"
echo "installed: $dest"
