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
#                                                       absent or newer than
#                                                       VERSION, WARNS if the
#                                                       version is older
#   - in an instance, every place that states the    → FAILS if any disagrees,
#     base version agrees, and its tag exists           if the tag is missing,
#                                                       or if base-version.yaml
#                                                       cannot be found;
#                                                       SKIPPED in a base-*
#                                                       repository
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
#   - a base repository names no instance            → FAILS on a hit of the
#     (scripts/leak-check.sh)                           denylist, WARNS that it
#                                                       is not active when no
#                                                       list is given, SKIPPED
#                                                       in an instance
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
# Uma versão à frente de VERSION afirma cumprir uma base que não existe
# (docs/ADAPTATION.md §7). Comparação campo a campo: o sort -V do macOS não é
# garantido.
_newer() {
    local IFS=.
    # shellcheck disable=SC2206
    local a=($1) b=($2) i
    for i in 0 1 2; do
        [ "${a[$i]}" -gt "${b[$i]}" ] && return 0
        [ "${a[$i]}" -lt "${b[$i]}" ] && return 1
    done
    return 1
}
if [ "$declared" = "$current" ]; then
    _ok "v$declared — igual à base atual"
elif _newer "$declared" "$current"; then
    _fail "declara v$declared, à frente da base atual v$current — a linha '# Base:' afirma cumprir uma versão que ainda não existe (docs/ADAPTATION.md §7)"
else
    _warn "declara v$declared; a base atual é v$current — ver base-platform/CHANGELOG.md antes de decidir se vale atualizar"
fi

# ── 2b. Pino da base, numa instância ─────────────────────────────────────────
# Uma instância diz em que versão da base roda em vários lugares: a linha
# '# Base:', <prefix>-platform/base-version.yaml, o @ref de um workflow de
# base-*, o ref de um checkout de base-*, o base_ref passado ao harmony e a
# tag de uma imagem base-*. Se discordam, ou se a tag não existe, o pino
# documenta uma esperança e não um fato (base-platform#38). Um repositório
# base-* não tem pino: ele É a versão.

_step "pino da base"
# O nome vem do remote (um worktree tem outro nome de diretório); sem remote,
# do diretório. O passo 7 também usa repo_name.
origin="$(git -C "$TARGET_DIR" remote get-url origin 2>/dev/null)" || origin=""
if [ -n "$origin" ]; then
    repo_name="$(basename "${origin%.git}")"
else
    repo_name="$(basename "$TARGET_DIR")"
fi
case "$repo_name" in
    base-*)
        _skip "$repo_name é um repositório da base — o pino é de cada instância"
        ;;
    *)
        # <prefix>-<camada>: o pino mora em <prefix>-platform, irmão deste.
        prefix="${repo_name%-*}"
        if [ "$repo_name" = "$prefix-platform" ]; then
            pin_file="$TARGET_DIR/base-version.yaml"
        else
            pin_file="$(dirname "$TARGET_DIR")/$prefix-platform/base-version.yaml"
        fi
        [ -f "$pin_file" ] || _fail "$repo_name é uma instância e $pin_file não existe — sem ele não há pino a conferir (docs/ADAPTATION.md §7)"
        pinned="$(python3 - "$pin_file" <<'PY'
import re
import sys

import yaml

with open(sys.argv[1], encoding="utf-8") as fh:
    value = str((yaml.safe_load(fh) or {}).get("base", ""))
if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
    sys.exit(f"{sys.argv[1]}: 'base: X.Y.Z' ausente ou malformado (achou {value!r})")
print(value)
PY
)" || _fail "base-version.yaml ilegível — veja acima"

        [ "$declared" = "$pinned" ] || _fail "AGENTS.md declara v$declared e $pin_file fixa $pinned — os dois dizem a mesma versão ou nenhum diz a verdade"

        # BASE_PLATFORM_REMOTE existe para os testes rodarem sem rede.
        remote="${BASE_PLATFORM_REMOTE:-}"
        if [ -z "$remote" ]; then
            remote="$(git -C "$BASE_PLATFORM_DIR" remote get-url origin)" \
                || _fail "$BASE_PLATFORM_DIR não tem remote origin — sem ele não sei onde procurar a tag v$pinned"
        fi
        tags="$(git ls-remote --tags "$remote" "refs/tags/v$pinned")" \
            || _fail "não consegui listar as tags de $remote — sem isso não sei se v$pinned existe"
        [ -n "$tags" ] || _fail "a tag v$pinned não existe em $remote — o pino aponta para uma versão nunca lançada (docs/ADAPTATION.md §7)"

        refs_ok=0
        python3 - "$TARGET_DIR" "v$pinned" <<'PY' || refs_ok=1
import re
import sys
from pathlib import Path

import yaml

root, want = Path(sys.argv[1]), sys.argv[2]
base_repo = re.compile(r"^[^/]+/base-[^/@]+")
bad, seen = [], 0


def walk(node, where):
    global seen
    if isinstance(node, list):
        for item in node:
            walk(item, where)
        return
    if not isinstance(node, dict):
        return
    uses = node.get("uses")
    with_ = node.get("with") if isinstance(node.get("with"), dict) else {}
    if isinstance(uses, str) and base_repo.match(uses) and "@" in uses:
        seen += 1
        if uses.rsplit("@", 1)[1] != want:
            bad.append(f"{where}: uses {uses} (esperado @{want})")
    if isinstance(uses, str) and uses.startswith("actions/checkout@"):
        repo = str(with_.get("repository", ""))
        if base_repo.fullmatch(repo):
            seen += 1
            if with_.get("ref") != want:
                bad.append(f"{where}: checkout de {repo} com ref {with_.get('ref')!r} (esperado {want})")
    if "base_ref" in with_:
        seen += 1
        if with_["base_ref"] != want:
            bad.append(f"{where}: base_ref {with_['base_ref']!r} (esperado {want})")
    for value in node.values():
        walk(value, where)


workflows = root / ".github" / "workflows"
for path in sorted([*workflows.glob("*.yml"), *workflows.glob("*.yaml")]):
    with open(path, encoding="utf-8") as fh:
        walk(yaml.safe_load(fh), path.relative_to(root))

# A tag de uma imagem base-*, literal ou no default de ARG BASE_TAG; um FROM
# que usa a variável é conferido pelo ARG.
arg = re.compile(r"^\s*ARG\s+BASE_TAG=(\S+)", re.I)
frm = re.compile(r"^\s*FROM\s+(?:--\S+\s+)*(?:\S*/)?base-[^:\s/]+:([^\s@]+)", re.I)
skip = {".git", "node_modules", ".venv"}
for path in sorted(root.rglob("Dockerfile*")) + sorted(root.rglob("*.Dockerfile")):
    if skip & set(path.relative_to(root).parts) or not path.is_file():
        continue
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        m = arg.match(line) or frm.match(line)
        if m and not m.group(1).startswith("$"):
            seen += 1
            if m.group(1) != want:
                bad.append(f"{path.relative_to(root)}:{n}: tag {m.group(1)} (esperado {want})")

if bad:
    print("\n".join(bad), file=sys.stderr)
    sys.exit(1)
print(f"{seen} referência(s) à base em workflows e Dockerfiles")
PY
        [ "$refs_ok" -eq 0 ] || _fail "uma referência à base discorda de base-version.yaml ($pinned) — veja acima"
        _ok "v$pinned — AGENTS.md, $pin_file, a tag e as referências concordam"
        ;;
esac

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
# operação) também conta, se existir — por nome genérico, não fixo: o nome
# do monólito precursor estava fixo aqui antes do rename para base-inference,
# e um novo CLI (ex. base-platform) nasceria invisível para este portão se o
# nome ficasse hardcoded de novo.
while IFS= read -r f; do
    shell_files+=("$f")
done < <(find "$TARGET_DIR" -maxdepth 1 -type f -perm -u+x ! -name '*.*' -print)

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

# ── 7. A base não nomeia instâncias ──────────────────────────────────────────
# A lista de nomes vem de fora (segredo BASE_DENYLIST no CI, ou um arquivo
# local em BASE_DENYLIST_FILE): escrita aqui, ela seria o vazamento. Numa
# instância a verificação não se aplica — ela se nomeia por definição.

_step "nomes de instância"
# repo_name vem do passo 2b.
case "$repo_name" in
    base-*)
        "$SCRIPT_DIR/leak-check.sh" "$TARGET_DIR" || _fail "um repositório da base nomeia uma instância — veja acima (base-platform#34)"
        ;;
    *)
        _skip "$repo_name não é um repositório base-* — a lista protege a base, não a instância"
        ;;
esac

echo ""
echo "${BOLD}${GREEN}Portão passou.${RESET} Pode abrir o PR."
echo ""
