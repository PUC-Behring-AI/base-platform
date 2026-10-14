#!/usr/bin/env bash
# =============================================================================
# scripts/release.sh — the only way the base is tagged
# =============================================================================
#
# Usage, from anywhere:
#   /path/to/base-platform/scripts/release.sh          # check, and say what it would tag
#   /path/to/base-platform/scripts/release.sh --tag    # check, then tag and push
#
# A tag v<VERSION> on the five base repositories means the combination
# fulfils that version and was tested against itself (docs/ADAPTATION.md §7).
# 0.3.0 and 0.4.0 were documented and never tagged, because nothing stopped
# VERSION from moving on without the five following it (base-platform#14).
# This script is what stops it: it tags only when every condition below holds,
# and tags exactly the commits it checked.
#
# Which repositories: base-platform, base-knowledge, base-inference,
# base-agents, base-interface, each the main checkout under BASE_ROOT
# (default: the parent of this base-platform). VERSION and CHANGELOG.md are
# read from BASE_ROOT/base-platform, the checkout being tagged, not from
# whichever working tree this script runs from.
#
# It refuses — exit 1, every reason listed — when any repository:
#   - is missing, or not on main, or has uncommitted changes
#   - is not at origin/main (after a fetch)
#   - declares a "# Base:" other than v<VERSION>
#   - already has the tag v<VERSION>, locally or on origin
# or when CHANGELOG.md does not give <VERSION> a date, or when harmony.sh
# fails on the set.
#
# Bash 3.2 compatible (the one macOS ships): no associative arrays.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_ROOT="$(cd "${BASE_ROOT:-$SCRIPT_DIR/../..}" && pwd)"
export BASE_ROOT

REPOS="base-platform base-knowledge base-inference base-agents base-interface"

tag_it=no
case "${1:-}" in
    "") ;;
    --tag) tag_it=yes ;;
    *) echo "usage: release.sh [--tag]" >&2; exit 2 ;;
esac

platform="$BASE_ROOT/base-platform"
[ -f "$platform/VERSION" ] || { echo "no VERSION in $platform" >&2; exit 1; }
version="$(tr -d '[:space:]' < "$platform/VERSION")"
tag="v$version"

problems=""
problem() { problems="$problems\n  - $*"; }

if ! grep -qE "^## \[$version\] — [0-9]{4}-[0-9]{2}-[0-9]{2}" "$platform/CHANGELOG.md"; then
    problem "CHANGELOG.md: '## [$version]' has no date — date it in a pull request before tagging"
fi

for name in $REPOS; do
    dir="$BASE_ROOT/$name"
    if [ ! -d "$dir/.git" ]; then
        problem "$name: no main checkout at $dir"
        continue
    fi
    branch="$(git -C "$dir" branch --show-current)"
    [ "$branch" = "main" ] || problem "$name: on '${branch:-(detached)}', not main"
    [ -z "$(git -C "$dir" status --porcelain)" ] || problem "$name: uncommitted changes"
    if git -C "$dir" fetch -q --tags origin main; then
        [ "$(git -C "$dir" rev-parse HEAD)" = "$(git -C "$dir" rev-parse origin/main)" ] \
            || problem "$name: HEAD is not origin/main"
        if git -C "$dir" ls-remote --exit-code --tags origin "refs/tags/$tag" >/dev/null 2>&1; then
            problem "$name: $tag already exists on origin"
        fi
    else
        problem "$name: could not fetch origin"
    fi
    if git -C "$dir" rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
        problem "$name: $tag already exists locally"
    fi
    declared="$(grep -m1 -oE '^# Base: v[0-9]+\.[0-9]+\.[0-9]+' "$dir/AGENTS.md" 2>/dev/null | sed -E 's/^# Base: //')" || true
    [ "$declared" = "$tag" ] || problem "$name: declares '${declared:-nothing}', not $tag"
done

if [ -n "$problems" ]; then
    printf "Not releasing %s:%b\n" "$tag" "$problems" >&2
    exit 1
fi

# Every repository is on main, so harmony runs the main checkouts.
if ! (cd "$platform" && "$SCRIPT_DIR/harmony.sh"); then
    echo "Not releasing $tag: harmony.sh failed on the set." >&2
    exit 1
fi

echo ""
for name in $REPOS; do
    echo "$name: $tag at $(git -C "$BASE_ROOT/$name" rev-parse --short HEAD)"
done

if [ "$tag_it" = "no" ]; then
    echo ""
    echo "Ready. Run again with --tag to tag and push."
    exit 0
fi

for name in $REPOS; do
    git -C "$BASE_ROOT/$name" tag -a "$tag" -m "base $tag"
done
for name in $REPOS; do
    git -C "$BASE_ROOT/$name" push -q origin "refs/tags/$tag"
    echo "$name: pushed $tag"
done
