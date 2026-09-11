#!/usr/bin/env bash
# =============================================================================
# scripts/gate.sh — the shared gate, for any repository in the base
# =============================================================================
#
# Usage, from inside the target repository:
#   /path/to/base-platform/scripts/gate.sh
#   /path/to/base-platform/scripts/gate.sh /path/to/some/other/repo
#
# In practice nobody calls it by that path. Every consuming repository installs
# a five-line wrapper at its own scripts/gate.sh (see docs/ADAPTATION.md,
# "Install the gate") that finds base-platform as a sibling directory — the
# same assumption compose.base.yaml already makes — and delegates here. That
# is the whole mechanism: one gate, several doors.
#
# Ten copies of a gate script diverge in the first week. That is the
# serve_config.yaml defect (base-inference's ARCHITECTURE §5.3, from before the
# rename) multiplied by ten, and it is the reason this file exists instead of
# being pasted into each repository.
#
# What it checks, and why each step can fail, warn, or skip:
#
#   - README.md and AGENTS.md exist                 → FAILS if missing
#   - AGENTS.md declares "# Base: vX.Y.Z"            → FAILS if the line is
#                                                       absent, WARNS if the
#                                                       version is not current
#   - every *.yml / *.yaml file parses               → FAILS if any is invalid
#   - a Python test suite, if one exists             → FAILS if red or if
#                                                       pytest is missing,
#                                                       SKIPPED if there is
#                                                       none yet
#   - Python lint (ruff), if any .py file exists      → FAILS if ruff finds
#                                                       something, SKIPPED if
#                                                       there is no code yet
#                                                       or ruff is absent
#   - shell scripts, if any exist                    → FAILS on syntax error,
#                                                       SKIPPED if there are
#                                                       none, shellcheck only
#                                                       if installed
#
# A repository with no code yet — every base-* engine on day one — passes on
# the first two checks alone. That is correct, not a loophole: there is
# nothing else to verify, and a gate that invents a floor to look thorough is
# a gate that lies about what it measured.
#
# The version check WARNS rather than FAILS on principle, from
# docs/ADAPTATION.md: "Staying behind is allowed... What is not allowed is not
# knowing." Blocking a PR because a repository has not yet upgraded would make
# the gate enforce a decision that belongs to whoever owns that repository.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_PLATFORM_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET_DIR="$(cd "${1:-$BASE_PLATFORM_DIR}" && pwd)"
cd "$TARGET_DIR"

if [ -t 1 ] && command -v tput &>/dev/null; then
    BOLD="$(tput bold)"; GREEN="$(tput setaf 2)"; RED="$(tput setaf 1)"
    YELLOW="$(tput setaf 3)"; RESET="$(tput sgr0)"
else
    BOLD="" GREEN="" RED="" YELLOW="" RESET=""
fi

_step() { echo ""; echo "${BOLD}── $* ──${RESET}"; }
_ok()   { echo "${GREEN}[ok]${RESET} $*"; }
_fail() { echo "${RED}[falhou]${RESET} $*" >&2; exit 1; }
_warn() { echo "${YELLOW}[atenção]${RESET} $*"; }
_skip() { echo "${YELLOW}[pulado]${RESET} $*"; }

echo "${BOLD}Portão compartilhado${RESET} — verificando $TARGET_DIR"

# ── 1. Documentos vivos ──────────────────────────────────────────────────────
# Um repositório sem uma linha de código ainda tem documentação que pode
# desincronizar. Isto é o piso que vale a partir do dia zero.

_step "documentos obrigatórios"
for f in README.md AGENTS.md; do
    [ -f "$TARGET_DIR/$f" ] || _fail "$f ausente — todo repositório da base nasce com README.md e AGENTS.md"
done
_ok "README.md e AGENTS.md presentes"

# ── 2. Versão da base declarada ──────────────────────────────────────────────
# AGENTS-base.md é versionado exatamente para que um repositório possa dizer
# contra qual base foi escrito, e para que "quem está atrasado?" tenha
# resposta. A ausência da linha é o defeito; estar atrasado não é.

_step "versão da base"
agents_file="$TARGET_DIR/AGENTS.md"
declared="$(grep -m1 -oE '^# Base: v[0-9]+\.[0-9]+\.[0-9]+' "$agents_file" 2>/dev/null | sed -E 's/^# Base: v//')" || true
if [ -z "${declared:-}" ]; then
    _fail "AGENTS.md não declara '# Base: vX.Y.Z' — sem essa linha, ninguém sabe contra qual versão da base este repositório foi escrito (issue base-platform#9)"
fi
current="$(cat "$BASE_PLATFORM_DIR/VERSION")"
if [ "$declared" = "$current" ]; then
    _ok "v$declared — igual à base atual"
else
    _warn "declara v$declared; a base atual é v$current — ver base-platform/CHANGELOG.md antes de decidir se vale atualizar"
fi

# ── 3. YAML válido ───────────────────────────────────────────────────────────

_step "arquivos YAML"
# `while read` em vez de `mapfile`: o bash da Apple é 3.2 (licença GPLv2),
# sem os builtins de array do bash 4+, e é o que qualquer pessoa do time roda
# por padrão num Mac.
yaml_files=()
while IFS= read -r f; do
    yaml_files+=("$f")
done < <(find "$TARGET_DIR" \
    -type d \( -name .git -o -name node_modules -o -name .venv \) -prune -o \
    -type f \( -name '*.yml' -o -name '*.yaml' \) -print | sort)

if [ "${#yaml_files[@]}" -eq 0 ]; then
    _skip "nenhum arquivo YAML neste repositório ainda"
else
    yaml_ok=0
    python3 - "${yaml_files[@]}" <<'PY' || yaml_ok=1
import sys
import yaml

failed = []
for path in sys.argv[1:]:
    try:
        with open(path, encoding="utf-8") as fh:
            list(yaml.safe_load_all(fh))
    except Exception as exc:  # noqa: BLE001
        failed.append(f"{path}: {exc}")

if failed:
    print("\n".join(failed), file=sys.stderr)
    sys.exit(1)
print(f"{len(sys.argv) - 1} arquivo(s) YAML parseiam")
PY
    [ "$yaml_ok" -eq 0 ] || _fail "um ou mais arquivos YAML não parseiam — veja acima"
    _ok "${#yaml_files[@]} arquivo(s) YAML válidos"
fi

# ── 4. Suíte Python, se existir ──────────────────────────────────────────────
# Nenhum piso de cobertura é imposto aqui: cada repositório declara o próprio,
# em pyproject.toml, quando tiver código o bastante para isso importar. Este
# gate roda o que existe — não inventa um piso para parecer rigoroso.

_step "suíte Python"
if [ -d "$TARGET_DIR/tests" ] && [ -f "$TARGET_DIR/pyproject.toml" ]; then
    if python3 -c 'import pytest' &>/dev/null; then
        python3 -m pytest -q || _fail "a suíte Python não passou"
        _ok "suíte Python verde"
    else
        _fail "tests/ e pyproject.toml existem mas pytest não está instalado — instale, não pule"
    fi
else
    _skip "sem pyproject.toml + tests/ — nada de Python para rodar ainda"
fi

# ── 5. Lint Python, se houver arquivo .py ────────────────────────────────────
# Achado ao escrever o primeiro consumidor real deste gate: ele checava a
# suíte, mas nunca o lint — uma dívida que ficaria invisível até acumular em
# três motores novos. Roda sobre TODO .py do repositório, não uma lista
# mantida à mão: uma lista de arquivos "limpos" é o mesmo problema do
# .gitignore por nome de arquivo, em outra roupa.

_step "lint Python"
py_files=()
while IFS= read -r f; do
    py_files+=("$f")
done < <(find "$TARGET_DIR" \
    -type d \( -name .git -o -name node_modules -o -name .venv -o -name __pycache__ \) -prune -o \
    -type f -name '*.py' -print | sort)

if [ "${#py_files[@]}" -eq 0 ]; then
    _skip "nenhum arquivo Python neste repositório ainda"
elif python3 -m ruff --version &>/dev/null; then
    python3 -m ruff check "${py_files[@]}" || _fail "ruff apontou erros"
    _ok "ruff limpo em ${#py_files[@]} arquivo(s)"
else
    # Skippable, matching shellcheck below and base-inference's own gate:
    # lint tools skip when absent, the way style checks do everywhere in this
    # base. Only the coverage floor (pytest-cov, in base-inference's gate)
    # fails hard when missing — that one measures whether anything was
    # verified at all, which lint does not.
    _skip "ruff não instalado (pip install ruff)"
fi

# ── 6. Scripts de shell, se existirem ────────────────────────────────────────

_step "scripts de shell"
shell_files=()
while IFS= read -r f; do
    shell_files+=("$f")
done < <(find "$TARGET_DIR" \
    -type d \( -name .git -o -name node_modules -o -name .venv \) -prune -o \
    -type f -name '*.sh' -print | sort)
# Um executável na raiz sem extensão (convenção deste projeto para o CLI de
# operação) também conta, se existir.
if [ -x "$TARGET_DIR/idia" ]; then
    shell_files+=("$TARGET_DIR/idia")
fi

if [ "${#shell_files[@]}" -eq 0 ]; then
    _skip "nenhum script de shell neste repositório ainda"
else
    for f in "${shell_files[@]}"; do
        bash -n "$f" || _fail "erro de sintaxe em $f"
    done
    _ok "${#shell_files[@]} script(s) sem erro de sintaxe"

    if command -v shellcheck &>/dev/null; then
        shellcheck -S error "${shell_files[@]}" || _fail "shellcheck apontou erros"
        _ok "shellcheck limpo"
    else
        _skip "shellcheck não instalado (brew install shellcheck)"
    fi
fi

# ── 6. Marca o portão ────────────────────────────────────────────────────────

if [ -x "$HOME/.claude/hooks/git-guard.sh" ]; then
    "$HOME/.claude/hooks/git-guard.sh" --stamp || true
fi

echo ""
echo "${BOLD}${GREEN}Portão passou.${RESET} Pode abrir o PR."
echo ""
