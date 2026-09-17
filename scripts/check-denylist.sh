#!/usr/bin/env bash
# Fails if any setting term from scripts/denylist.txt appears in engine code.
# Usage: scripts/check-denylist.sh [path ...]   (defaults to crates wit plugins client/src)
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
list="$root/scripts/denylist.txt"
if [ "$#" -gt 0 ]; then paths=("$@"); else paths=(crates wit plugins client/src); fi

cd "$root"
existing=()
for p in "${paths[@]}"; do [ -e "$p" ] && existing+=("$p"); done
[ "${#existing[@]}" -eq 0 ] && { echo "denylist: nothing to scan"; exit 0; }

status=0
while IFS= read -r line; do
  line="${line%%#*}"
  line="$(echo "$line" | tr -d '[:space:]')"
  [ -z "$line" ] && continue
  mode="${line%%:*}"
  term="${line#*:}"
  # Word boundary that also splits snake_case: term must not touch a letter or digit.
  pattern="(^|[^[:alnum:]])${term}s?([^[:alnum:]]|$)"
  case "$mode" in
    i) flags=(-rniE) ;;
    c) flags=(-rnE) ;;
    *) echo "denylist: bad line '$line' (expected i:term or c:term)"; exit 2 ;;
  esac
  if hits="$(grep "${flags[@]}" --exclude-dir=target -- "$pattern" "${existing[@]}")"; then
    echo "denylist: setting term '$term' found in engine code:"
    echo "$hits" | sed 's/^/  /'
    status=1
  fi
done < "$list"

[ "$status" -eq 0 ] && echo "denylist: clean (${existing[*]})"
exit "$status"
