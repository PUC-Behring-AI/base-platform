#!/usr/bin/env bash
# =============================================================================
# scripts/publish-release.sh — a release's charts and engine images, as files
# =============================================================================
#
# Usage, from anywhere:
#   scripts/publish-release.sh vX.Y.Z                    # build, say what it would attach
#   scripts/publish-release.sh vX.Y.Z --upload           # build, then attach
#   scripts/publish-release.sh vX.Y.Z --upload --replace # also replace a differing asset
#   ... [--platforms linux/arm64,linux/amd64]            # the default: both
#
# An instance that runs a tagged base needs each engine's chart and image,
# not its source. This script builds them from the tag and attaches them to
# that tag's GitHub Release in each engine repository: base-knowledge,
# base-inference, base-agents, base-interface. base-platform's release gets
# nothing; its files are public at the tag.
#
# Per engine repository:
#   <chart>-X.Y.Z.tgz                      helm package of deploy/chart
#   <image>-vX.Y.Z-linux-<arch>.tar.gz     docker image, one per platform
#   manifest.json                          repo, tag, commit, chart, images
#   SHA256SUMS                             shasum -a 256 of the three above
# in ${XDG_CACHE_HOME:-$HOME/.cache}/base-publish/vX.Y.Z/<repo>/, and beside
# them lock.sha256: "<sha256>  <repo>/<file>" for every asset, under the
# header "# base vX.Y.Z", printed at the end for an instance to pin.
#
# Everything is built from `git archive <tag>`, never from a working tree.
# The repositories are the checkouts under BASE_ROOT (default: the parent of
# this base-platform), as for release.sh.
#
# It refuses — exit 1, every reason listed — when, in any of the five:
#   - the tag is missing, or lightweight (release.sh makes annotated tags)
#   - the local tag's commit is not the one origin's tag points to
# or when base-platform's VERSION at the tag is not X.Y.Z, an engine's
# deploy/chart/Chart.yaml at the tag is not version X.Y.Z, or CHANGELOG.md
# at the tag has no section for X.Y.Z (the release notes).
#
# A re-run reuses a file already in the output directory only when it was
# built from the same commit and its sha256 still matches the one recorded in
# SHA256SUMS; anything else is rebuilt.
#
# --upload creates the release when it is missing, then attaches each asset.
# An asset of the same name already attached is skipped when its digest
# matches, and refused when it differs — unless --replace, which replaces it.
# The refusal comes before anything is uploaded to any repository.
#
# Bash 3.2 compatible (the one macOS ships): no associative arrays.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_ROOT="$(cd "${BASE_ROOT:-$SCRIPT_DIR/../..}" && pwd)"

# <repository> <image> <build context, relative to the repository>. The Ray
# image (base-inference's Dockerfile.ray) is not an engine image an instance
# loads; it is built where a GPU cluster pulls it.
ENGINES="base-knowledge:base-knowledge:.
base-inference:base-inference-stand-in:stand-in
base-agents:base-agents:.
base-interface:base-interface:."
REPOS="base-platform base-knowledge base-inference base-agents base-interface"
BUILDER=base-multiarch

die() { echo "publish-release: $*" >&2; exit 1; }
usage() {
    echo "usage: publish-release.sh vX.Y.Z [--platforms linux/arm64,linux/amd64] [--upload] [--replace]" >&2
    exit 2
}

tag=""
platforms="linux/arm64,linux/amd64"
upload=no
replace=no
while [ $# -gt 0 ]; do
    case "$1" in
        --upload) upload=yes ;;
        --replace) replace=yes ;;
        --platforms)
            [ $# -ge 2 ] || usage
            platforms="$2"
            shift
            ;;
        v*) [ -z "$tag" ] || usage; tag="$1" ;;
        *) usage ;;
    esac
    shift
done
[ -n "$tag" ] || usage
echo "$tag" | grep -qE '^v[0-9]+\.[0-9]+\.[0-9]+$' || die "'$tag' is not vX.Y.Z"
version="${tag#v}"
[ "$replace" = "no" ] || [ "$upload" = "yes" ] || die "--replace only means something with --upload"

archs=""
for p in $(echo "$platforms" | tr ',' ' '); do
    case "$p" in
        linux/arm64|linux/amd64) archs="$archs ${p#linux/}" ;;
        *) die "platform '$p' is not linux/arm64 or linux/amd64" ;;
    esac
done
[ -n "$archs" ] || die "--platforms names no platform"

platform="$BASE_ROOT/base-platform"
work="$(mktemp -d "${TMPDIR:-/tmp}/publish-release.XXXXXX")"
trap 'rm -rf "$work"' EXIT

# --- Refusals: every reason, then exit -----------------------------------------

problems=""
problem() { problems="$problems\n  - $*"; }

for name in $REPOS; do
    dir="$BASE_ROOT/$name"
    if [ ! -d "$dir/.git" ]; then
        problem "$name: no checkout at $dir"
        continue
    fi
    if ! git -C "$dir" rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
        problem "$name: no tag $tag (git fetch --tags?)"
        continue
    fi
    if [ "$(git -C "$dir" cat-file -t "refs/tags/$tag")" != "tag" ]; then
        problem "$name: $tag is a lightweight tag, not an annotated one"
    fi
    local_commit="$(git -C "$dir" rev-parse "$tag^{commit}")"
    if ! remote="$(git -C "$dir" ls-remote origin "refs/tags/$tag^{}")"; then
        problem "$name: could not read $tag from origin"
        continue
    fi
    remote_commit="$(echo "$remote" | awk '{print $1}')"
    if [ -z "$remote_commit" ]; then
        problem "$name: origin has no annotated $tag"
    elif [ "$remote_commit" != "$local_commit" ]; then
        problem "$name: local $tag is $local_commit, origin's is $remote_commit"
    fi
    if [ "$name" = "base-platform" ]; then
        declared="$(git -C "$dir" show "$tag:VERSION" 2>/dev/null | tr -d '[:space:]')" || true
        [ "$declared" = "$version" ] ||
            problem "base-platform: VERSION at $tag is '${declared:-nothing}', not $version"
        git -C "$dir" show "$tag:CHANGELOG.md" > "$work/changelog" 2>/dev/null || : > "$work/changelog"
        awk -v h="## [$version]" 'index($0, h) == 1 {on = 1; next} on && /^## \[/ {exit} on' \
            "$work/changelog" > "$work/notes.md"
        grep -q '[^[:space:]]' "$work/notes.md" ||
            problem "base-platform: CHANGELOG.md at $tag has no section for $version"
    else
        chart_version="$(git -C "$dir" show "$tag:deploy/chart/Chart.yaml" 2>/dev/null |
            sed -n 's/^version: *"\{0,1\}\([^"]*\)"\{0,1\} *$/\1/p')" || true
        [ "$chart_version" = "$version" ] ||
            problem "$name: deploy/chart/Chart.yaml at $tag is version '${chart_version:-nothing}', not $version"
    fi
done

if [ -n "$problems" ]; then
    printf "Not publishing %s:%b\n" "$tag" "$problems" >&2
    exit 1
fi

# The organisation the engines' releases live in: base-platform's own. The
# configured URL, not `git remote get-url`, which applies url.insteadOf.
origin_url="$(git -C "$platform" config --get remote.origin.url)" || die "base-platform has no origin"
owner="$(echo "$origin_url" | sed -n 's#^.*github\.com[:/]\([^/]*\)/[^/]*$#\1#p')"
[ -n "$owner" ] || die "base-platform's origin ($origin_url) is not a github.com repository"

# --- Build ---------------------------------------------------------------------

docker buildx inspect "$BUILDER" >/dev/null ||
    die "no buildx builder '$BUILDER' (docker buildx create --name $BUILDER --driver docker-container)"

OUT="${XDG_CACHE_HOME:-$HOME/.cache}/base-publish/$tag"
mkdir -p "$OUT"

sum_of() { shasum -a 256 "$1" | awk '{print $1}'; }

# The sha256 SHA256SUMS records for a file, or nothing.
recorded() {
    [ -f "$2/SHA256SUMS" ] || return 0
    awk -v f="$1" '$2 == f {print $1}' "$2/SHA256SUMS"
}

# Record a file's sha256 in SHA256SUMS as soon as it is built, so a run cut
# short keeps what it finished.
record() {
    local file="$1" dir="$2" sum
    sum="$(sum_of "$dir/$file")"
    { [ ! -f "$dir/SHA256SUMS" ] || awk -v f="$file" '$2 != f' "$dir/SHA256SUMS"
      echo "$sum  $file"; } > "$dir/SHA256SUMS.new"
    mv "$dir/SHA256SUMS.new" "$dir/SHA256SUMS"
}

reusable() {
    local file="$1" dir="$2" want
    [ -f "$dir/$file" ] || return 1
    want="$(recorded "$file" "$dir")"
    [ -n "$want" ] || return 1
    [ "$(sum_of "$dir/$file")" = "$want" ]
}

assets_of() { awk '{print $2}' "$1/SHA256SUMS"; }

: > "$work/lock"
while IFS=: read -r name image context; do
    repo_dir="$BASE_ROOT/$name"
    commit="$(git -C "$repo_dir" rev-parse "$tag^{commit}")"
    dir="$OUT/$name"
    mkdir -p "$dir"
    # Files built from another commit are not this release's.
    if [ "$(cat "$dir/.source" 2>/dev/null || true)" != "$commit" ]; then
        rm -f "$dir"/*
        echo "$commit" > "$dir/.source"
    fi

    src="$work/$name"
    mkdir -p "$src"
    git -C "$repo_dir" archive "$tag" | tar -x -C "$src"

    chart_name="$(sed -n 's/^name: *"\{0,1\}\([^"]*\)"\{0,1\} *$/\1/p' "$src/deploy/chart/Chart.yaml")"
    [ -n "$chart_name" ] || die "$name: deploy/chart/Chart.yaml at $tag has no name"
    chart_file="$chart_name-$version.tgz"
    if reusable "$chart_file" "$dir"; then
        echo "$name: $chart_file (reused)"
    else
        rm -f "$dir/$chart_file"
        helm package "$src/deploy/chart" -d "$work/charts-$name" >/dev/null
        [ -f "$work/charts-$name/$chart_file" ] || die "$name: helm package did not write $chart_file"
        mv "$work/charts-$name/$chart_file" "$dir/$chart_file"
        record "$chart_file" "$dir"
        echo "$name: $chart_file (built)"
    fi

    image_rows=""
    for arch in $archs; do
        file="$image-$tag-linux-$arch.tar.gz"
        if reusable "$file" "$dir"; then
            echo "$name: $file (reused)"
        else
            rm -f "$dir/$file"
            echo "$name: building $image:$tag for linux/$arch"
            docker buildx build --builder "$BUILDER" --platform "linux/$arch" \
                --label "org.opencontainers.image.version=$tag" \
                --label "org.opencontainers.image.revision=$commit" \
                --output "type=docker,name=$image:$tag,dest=$work/$image-$arch.tar" \
                "$src/$context"
            [ -s "$work/$image-$arch.tar" ] || die "$name: docker wrote no image for linux/$arch"
            gzip -n -c "$work/$image-$arch.tar" > "$dir/$file.partial"
            rm -f "$work/$image-$arch.tar"
            mv "$dir/$file.partial" "$dir/$file"
            record "$file" "$dir"
            echo "$name: $file (built)"
        fi
        image_rows="$image_rows$image:$tag linux/$arch $file $(recorded "$file" "$dir")
"
    done

    python3 - "$dir/manifest.json" "$name" "$tag" "$commit" \
        "$chart_file" "$chart_name" "$version" "$(recorded "$chart_file" "$dir")" "$image_rows" <<'PY'
import json
import sys

out, repo, tag, commit, chart_file, chart_name, version, chart_sum, rows = sys.argv[1:]
images = []
for row in rows.splitlines():
    ref, platform, file, sha = row.split()
    images.append({"ref": ref, "platform": platform, "file": file, "sha256": sha})
manifest = {
    "repo": repo,
    "tag": tag,
    "commit": commit,
    "chart": {"file": chart_file, "name": chart_name, "version": version, "sha256": chart_sum},
    "images": images,
}
with open(out, "w") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")
PY

    # SHA256SUMS lists exactly this run's assets, a file a previous run built
    # for another platform included only if this run asked for it.
    {
        echo "$(recorded "$chart_file" "$dir")  $chart_file"
        for arch in $archs; do
            file="$image-$tag-linux-$arch.tar.gz"
            echo "$(recorded "$file" "$dir")  $file"
        done
        echo "$(sum_of "$dir/manifest.json")  manifest.json"
    } > "$dir/SHA256SUMS.new"
    mv "$dir/SHA256SUMS.new" "$dir/SHA256SUMS"
    (cd "$dir" && shasum -a 256 -c --quiet SHA256SUMS) || die "$name: SHA256SUMS does not match the files in $dir"

    for file in $(assets_of "$dir") SHA256SUMS; do
        echo "$(sum_of "$dir/$file")  $name/$file" >> "$work/lock"
    done
done <<EOF
$ENGINES
EOF

{ echo "# base $tag"; cat "$work/lock"; } > "$OUT/lock.sha256"

# --- Plan, or upload -----------------------------------------------------------

size_of() {
    wc -c < "$1" | LC_ALL=C awk '$1 < 1048576 {printf "%.1f KB", $1 / 1024; next} {printf "%.1f MB", $1 / 1048576}'
}

echo ""
while IFS=: read -r name image context; do
    dir="$OUT/$name"
    echo "$owner/$name release $tag:"
    for file in $(assets_of "$dir") SHA256SUMS; do
        echo "  $file ($(size_of "$dir/$file"))"
    done
done <<EOF
$ENGINES
EOF
echo "base-platform: no assets."

if [ "$upload" = "yes" ]; then
    # What each release already has: "<name> <digest>" per asset, or "missing".
    conflicts=""
    while IFS=: read -r name image context; do
        if attached="$(gh api "repos/$owner/$name/releases/tags/$tag" \
            --jq '.assets[] | "\(.name) \(.digest)"' 2>"$work/gh.err")"; then
            echo "$attached" > "$work/attached-$name"
        elif grep -q "HTTP 404" "$work/gh.err"; then
            echo "missing" > "$work/attached-$name"
        else
            cat "$work/gh.err" >&2
            die "$name: cannot read release $tag from $owner/$name"
        fi
        : > "$work/new-$name"
        : > "$work/clobber-$name"
        dir="$OUT/$name"
        for file in $(assets_of "$dir") SHA256SUMS; do
            have="$(awk -v f="$file" '$1 == f {print $2}' "$work/attached-$name")"
            want="sha256:$(sum_of "$dir/$file")"
            if [ -z "$have" ]; then
                echo "$dir/$file" >> "$work/new-$name"
            elif [ "$have" = "$want" ]; then
                echo "$name: $file already attached, same digest"
            else
                echo "$dir/$file" >> "$work/clobber-$name"
                conflicts="$conflicts\n  - $name: $file is attached with $have, built $want"
            fi
        done
    done <<EOF
$ENGINES
EOF
    if [ -n "$conflicts" ] && [ "$replace" = "no" ]; then
        printf "Not uploading: attached assets differ (--replace replaces them):%b\n" "$conflicts" >&2
        exit 1
    fi

    while IFS=: read -r name image context; do
        if [ "$(cat "$work/attached-$name")" = "missing" ]; then
            gh release create "$tag" --verify-tag -R "$owner/$name" \
                --title "base $tag" --notes-file "$work/notes.md"
            echo "$name: created release $tag"
        fi
        if [ -s "$work/new-$name" ]; then
            # shellcheck disable=SC2046 # one path per line, no spaces
            gh release upload "$tag" -R "$owner/$name" $(cat "$work/new-$name")
            echo "$name: attached $(wc -l < "$work/new-$name" | tr -d ' ') asset(s)"
        fi
        if [ -s "$work/clobber-$name" ]; then
            # shellcheck disable=SC2046 # one path per line, no spaces
            gh release upload "$tag" -R "$owner/$name" --clobber $(cat "$work/clobber-$name")
            echo "$name: replaced $(wc -l < "$work/clobber-$name" | tr -d ' ') asset(s)"
        fi
    done <<EOF
$ENGINES
EOF
else
    echo ""
    echo "Dry run: nothing uploaded. Run again with --upload to attach."
fi

echo ""
echo "$OUT/lock.sha256:"
cat "$OUT/lock.sha256"
