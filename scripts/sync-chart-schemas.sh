#!/usr/bin/env bash
# =============================================================================
# scripts/sync-chart-schemas.sh — refresh the schemas chart's copy of schemas/
# =============================================================================
#
# Usage, from anywhere:
#   scripts/sync-chart-schemas.sh
#
# Helm cannot read files outside the chart, so deploy/charts/schemas/files/ is
# a checked-in copy of schemas/*.json. tests/test_platform_charts.py fails when
# the copy differs from schemas/. Only *.json is copied.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/deploy/charts/schemas/files"

mkdir -p "$DEST"
rm -f "$DEST"/*.json
cp "$ROOT"/schemas/*.json "$DEST"/
echo "synced $(find "$DEST" -name '*.json' | wc -l | tr -d ' ') schema(s) into ${DEST#"$ROOT"/}"
