#!/usr/bin/env bash
# =============================================================================
# scripts/leak-check.sh — fails when a base repository names an instance
# =============================================================================
#
# Usage:
#   scripts/leak-check.sh [/path/to/repo]
#
# The base must not be able to tell which projects use it (README.md). A
# denylist of the names that would tell it cannot live in this public
# repository — writing it here would be the leak — so it comes from outside:
#
#   BASE_DENYLIST       the terms, one per line (a CI secret)
#   BASE_DENYLIST_FILE  a file holding them, one per line (a local run)
#
# What it scans, case-insensitively and on word boundaries:
#   - every tracked path and every tracked text file (git ls-files);
#   - when LEAK_CHECK_RANGE is set (base..head), the commit messages in it;
#   - when PR_BODY is set, the pull request's body.
#
# A hit is reported by place (file:line, commit, body line) and by the
# term's position in the list ("termo #3"), never by the term or the line:
# this repository's CI logs are public, and printing the match would publish
# the list it protects. A path that itself contains a term is reported by
# its position in `git ls-files`, for the same reason.
#
# Neither variable set: the check is NOT active, and says so loudly. It does
# not pass silently as if it had looked.
# =============================================================================

set -euo pipefail

TARGET_DIR="$(cd "${1:-.}" && pwd)"

_warn() { echo "[atenção] $*"; }
_fail() { echo "[falhou] $*" >&2; exit 1; }

if [ -n "${BASE_DENYLIST:-}" ]; then
    raw="$BASE_DENYLIST"
elif [ -n "${BASE_DENYLIST_FILE:-}" ]; then
    [ -f "$BASE_DENYLIST_FILE" ] || _fail "BASE_DENYLIST_FILE aponta para um arquivo que não existe: $BASE_DENYLIST_FILE"
    raw="$(cat "$BASE_DENYLIST_FILE")"
else
    _warn "verificação de nomes NÃO está ativa — nem BASE_DENYLIST nem BASE_DENYLIST_FILE definidos; nada foi verificado"
    if [ -n "${GITHUB_ACTIONS:-}" ]; then
        echo "::warning::leak check is NOT active: neither BASE_DENYLIST nor BASE_DENYLIST_FILE is set"
    fi
    exit 0
fi

# Um termo por linha; linhas em branco e espaços nas pontas não contam.
terms=()
while IFS= read -r t; do
    t="$(printf '%s' "$t" | tr -d '\r' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
    [ -n "$t" ] && terms+=("$t")
done <<<"$raw"
[ "${#terms[@]}" -gt 0 ] || _fail "a lista de termos está definida mas vazia — nada a verificar é um erro, não um passe"

paths=()
while IFS= read -r p; do
    paths+=("$p")
done < <(git -C "$TARGET_DIR" ls-files)

hits=0
_hit() { echo "  $*" >&2; hits=$((hits + 1)); }

# Caminhos que contêm um termo: reportados pela posição, nunca pelo nome.
redacted=" "
if [ "${#paths[@]}" -gt 0 ]; then
    for j in "${!terms[@]}"; do
        while IFS= read -r n; do
            _hit "caminho nº $n de git ls-files: termo #$((j + 1))"
            redacted="$redacted${paths[$((n - 1))]} "
        done < <(printf '%s\n' "${paths[@]}" | grep -niwF -e "${terms[$j]}" | cut -d: -f1 || true)
    done
fi

for j in "${!terms[@]}"; do
    # git grep -n imprime arquivo:linha:conteúdo; só arquivo:linha sai daqui.
    while IFS= read -r loc; do
        file="${loc%:*}"
        case "$redacted" in
            *" $file "*) loc="(caminho com termo):${loc##*:}" ;;
        esac
        _hit "$loc: termo #$((j + 1))"
    done < <(git -C "$TARGET_DIR" grep -n -I -i -w -F -e "${terms[$j]}" | cut -d: -f1,2 || true)
done

if [ -n "${LEAK_CHECK_RANGE:-}" ]; then
    commits="$(git -C "$TARGET_DIR" log --format=%H "$LEAK_CHECK_RANGE")" \
        || _fail "LEAK_CHECK_RANGE=$LEAK_CHECK_RANGE não é um intervalo que o git resolve"
    for sha in $commits; do
        msg="$(git -C "$TARGET_DIR" log -1 --format=%B "$sha")"
        for j in "${!terms[@]}"; do
            while IFS= read -r n; do
                _hit "mensagem do commit ${sha:0:7}, linha $n: termo #$((j + 1))"
            done < <(printf '%s\n' "$msg" | grep -niwF -e "${terms[$j]}" | cut -d: -f1 || true)
        done
    done
fi

if [ -n "${PR_BODY:-}" ]; then
    for j in "${!terms[@]}"; do
        while IFS= read -r n; do
            _hit "corpo do PR, linha $n: termo #$((j + 1))"
        done < <(printf '%s\n' "$PR_BODY" | grep -niwF -e "${terms[$j]}" | cut -d: -f1 || true)
    done
fi

if [ "$hits" -gt 0 ]; then
    _fail "$hits ocorrência(s) de termos da lista — a base não pode nomear quem a usa (README.md)"
fi
echo "[ok] nenhum dos ${#terms[@]} termo(s) da lista em ${#paths[@]} arquivo(s)${LEAK_CHECK_RANGE:+, nos commits de $LEAK_CHECK_RANGE}${PR_BODY:+ e no corpo do PR}"
