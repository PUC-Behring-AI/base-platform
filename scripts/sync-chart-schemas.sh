#!/usr/bin/env bash
# =============================================================================
# scripts/sync-chart-schemas.sh — refresh the schemas chart's copy of schemas/
# =============================================================================
#
# Usage, from anywhere:
#   scripts/sync-chart-schemas.sh
#
# Helm cannot read files outside the chart, so deploy/charts/schemas/files/ is
# a checked-in copy of what the layers read from schemas/:
# every *.json and validate.py (a ConfigMap mounted over the schemas directory
# shadows all of it). README.md and __pycache__ are not copied.
# tests/test_platform_charts.py fails when the copy differs from schemas/.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/deploy/charts/schemas/files"

mkdir -p "$DEST"
rm -f "$DEST"/*
cp "$ROOT"/schemas/*.json "$ROOT"/schemas/validate.py "$DEST"/
echo "synced $(find "$DEST" -type f | wc -l | tr -d ' ') file(s) into ${DEST#"$ROOT"/}"
