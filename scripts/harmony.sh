#!/usr/bin/env bash
# =============================================================================
# scripts/harmony.sh — run every sibling repository's gate, together
# =============================================================================
#
# Usage, from anywhere:
#   /path/to/base-platform/scripts/harmony.sh [repo-path ...]
#
# The repositories of the base and of every instance are one system
# (AGENTS-base.md, Axiom 10): a change to a schema, a contract, an instance
# file shape or an env var name in one of them can break a sibling whose own
# gate never ran. Each repository's gate checks that repository alone. This
# script checks the set: it runs every sibling's gate against the working
# trees as they are on disk, so a change is measured against the siblings it
# can break before it is proposed, not after it is merged.
#
# Which repositories:
#   every directory under BASE_ROOT (default: the parent of this
#   base-platform) whose AGENTS.md declares "# Base: vX.Y.Z". Each is named
#   after its origin remote, so a worktree and its main checkout are the same
#   repository. When both exist, the main checkout is used — unless a path is
#   given on the command line, or the current directory is inside one of
#   them: then that working tree is used instead. Run it from the worktree you
#   are changing, and the siblings are checked against your change.
#
# What it exports to every gate, so the cross-layer checks use the same set:
#   BASE_ROOT, and BASE_<NAME>_DIR for every base-* repository
#   (BASE_PLATFORM_DIR, BASE_KNOWLEDGE_DIR, ...) — the variables the gate
#   wrappers, schema_bridge.py and base-agents' tests already read.
#
# What it reports, and when it fails:
#   - a repository without scripts/gate.sh                → FAILS
#   - a gate that fails                                    → FAILS
#   - a repository off its default branch, or with
#     uncommitted changes                                  → WARNS (you are
#     testing against work that is not on main; that is
#     fine for the one you are changing, and worth
#     knowing for any other)
#   - "# Base:" lines that differ between repositories     → WARNS
#
# Bash 3.2 compatible (the one macOS ships): no associative arrays.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
THIS_PLATFORM_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BASE_ROOT="$(cd "${BASE_ROOT:-$THIS_PLATFORM_DIR/..}" && pwd)"
export BASE_ROOT

if [ -t 1 ] && command -v tput &>/dev/null; then
    BOLD="$(tput bold)"; GREEN="$(tput setaf 2)"; RED="$(tput setaf 1)"
    YELLOW="$(tput setaf 3)"; RESET="$(tput sgr0)"
else
    BOLD="" GREEN="" RED="" YELLOW="" RESET=""
fi

# The repository a working tree belongs to: its origin remote's name, or —
# with no remote (a fresh clone, a test fixture) — the name of the main
# checkout's directory, which a worktree shares through its common git dir.
repo_name() {
    local dir="$1" url common
    url="$(git -C "$dir" remote get-url origin 2>/dev/null || true)"
    if [ -n "$url" ]; then
        url="${url%.git}"
        echo "${url##*/}"
        return 0
    fi
    common="$(cd "$dir" && git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
    if [ -n "$common" ]; then
        basename "$(dirname "$common")"
    else
        basename "$dir"
    fi
}

is_member() {
    [ -f "$1/AGENTS.md" ] && grep -qE '^# Base: v[0-9]+\.[0-9]+\.[0-9]+' "$1/AGENTS.md"
}

is_worktree() {
    [ -f "$1/.git" ]
}

# ── 1. Which working trees ───────────────────────────────────────────────────

# Preferred working trees: the command-line paths, plus the repository the
# current directory is in.
preferred=()
for p in "$@"; do
    [ -d "$p" ] || { echo "${RED}not a directory:${RESET} $p" >&2; exit 2; }
    p="$(cd "$p" && pwd)"
    is_member "$p" || { echo "${RED}not a repository of the base (no '# Base:' line in AGENTS.md):${RESET} $p" >&2; exit 2; }
    preferred+=("$p")
done
here="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -n "$here" ] && is_member "$here"; then
    preferred+=("$here")
fi

names=()
paths=()
# Index of a name in names[], or nothing.
index_of() {
    local i
    for i in "${!names[@]}"; do
        if [ "${names[$i]}" = "$1" ]; then echo "$i"; return 0; fi
    done
    return 0
}
consider() {
    local dir="$1" force="$2" name i
    name="$(repo_name "$dir")"
    i="$(index_of "$name")"
    if [ -z "$i" ]; then
        names+=("$name"); paths+=("$dir")
    elif [ "$force" = "yes" ]; then
        paths[i]="$dir"
    elif is_worktree "${paths[$i]}" && ! is_worktree "$dir"; then
        paths[i]="$dir"
    fi
}

# A layer-named repository with no "# Base:" line is not skipped in silence:
# it is a repository of the system that cannot say which base it follows.
unlisted=""
for dir in "$BASE_ROOT"/*/; do
    dir="${dir%/}"
    if is_member "$dir"; then
        consider "$dir" no
    elif [ -e "$dir/.git" ]; then
        case "$(basename "$dir")" in
            base-*|*-platform|*-knowledge|*-inference|*-agents|*-interface)
                unlisted="$unlisted $(basename "$dir")" ;;
        esac
    fi
done
for dir in ${preferred[@]+"${preferred[@]}"}; do
    consider "$dir" yes
done

if [ "${#names[@]}" -eq 0 ]; then
    echo "${RED}no repository of the base found under $BASE_ROOT${RESET}" >&2
    exit 1
fi

# ── 2. The variables every gate sees ────────────────────────────────────────

for i in "${!names[@]}"; do
    case "${names[$i]}" in
        base-*)
            var="$(echo "${names[$i]}" | tr '[:lower:]-' '[:upper:]_')_DIR"
            export "$var=${paths[$i]}"
            ;;
    esac
done

# ── 3. Run every gate ────────────────────────────────────────────────────────

LOG_DIR="$(mktemp -d "${TMPDIR:-/tmp}/harmony.XXXXXX")"
echo "${BOLD}Harmony${RESET} — ${#names[@]} repositories under $BASE_ROOT (logs: $LOG_DIR)"

failed=0
warned=0
versions=""
summary=""
for i in "${!names[@]}"; do
    name="${names[$i]}"; dir="${paths[$i]}"
    branch="$(git -C "$dir" branch --show-current 2>/dev/null || echo '?')"
    [ -n "$branch" ] || branch="(detached)"
    default="$(git -C "$dir" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null || echo origin/main)"
    default="${default#origin/}"
    dirty="$(git -C "$dir" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
    version="$(grep -m1 -oE '^# Base: v[0-9]+\.[0-9]+\.[0-9]+' "$dir/AGENTS.md" | sed -E 's/^# Base: //')"
    case " $versions " in *" $version "*) ;; *) versions="$versions $version" ;; esac

    note=""
    if [ "$branch" != "$default" ] || [ "$dirty" != "0" ]; then
        note="off $default ($branch, $dirty uncommitted)"
        warned=1
    fi

    echo ""
    echo "${BOLD}── $name${RESET} ($dir)"
    log="$LOG_DIR/$name.log"
    if [ ! -x "$dir/scripts/gate.sh" ]; then
        result="FAIL (no scripts/gate.sh)"
        failed=1
        echo "${RED}[fail]${RESET} no scripts/gate.sh — every repository of the base has one (ADAPTATION §3)"
    elif (cd "$dir" && ./scripts/gate.sh) >"$log" 2>&1; then
        result="pass"
        echo "${GREEN}[pass]${RESET} gate"
    else
        result="FAIL (see $log)"
        failed=1
        echo "${RED}[fail]${RESET} gate — last lines of $log:"
        tail -n 15 "$log" | sed 's/^/    /'
    fi
    if [ -n "$note" ]; then echo "${YELLOW}[warn]${RESET} $note"; fi
    summary="$summary| $name | $branch | $version | $result | $note |\n"
done

# ── 4. Summary ───────────────────────────────────────────────────────────────

echo ""
echo "${BOLD}Summary${RESET} (paste into the pull request)"
echo ""
echo "| repository | branch | base | gate | notes |"
echo "|---|---|---|---|---|"
printf "%b" "$summary"

if [ -n "$unlisted" ]; then
    warned=1
    echo ""
    echo "${YELLOW}[warn]${RESET} not checked — layer-named, but no '# Base:' line in AGENTS.md:$unlisted"
fi

if [ "$(echo "$versions" | wc -w | tr -d ' ')" -gt 1 ]; then
    warned=1
    echo ""
    echo "${YELLOW}[warn]${RESET} the repositories declare different base versions:$versions"
fi

echo ""
if [ "$failed" -ne 0 ]; then
    echo "${BOLD}${RED}Harmony failed.${RESET} A sibling's gate is red with these working trees."
    exit 1
fi
if [ "$warned" -ne 0 ]; then
    echo "${BOLD}${GREEN}Harmony passed${RESET}, with warnings above."
else
    echo "${BOLD}${GREEN}Harmony passed.${RESET}"
fi
