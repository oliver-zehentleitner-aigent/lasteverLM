#!/bin/sh
# Renders build/lasteverlm-handbook.pdf from the repository's docs
# (scripts/handbook/build.mjs) in the Playwright image: Markdown to HTML with
# marked, then Chromium's page.pdf. Needs Docker. VERSION: the latest tag;
# DATE: today (UTC).
set -eu
here=$(cd "$(dirname "$0")" && pwd)
repo=${REPO_ROOT:-$(cd "$here/../.." && pwd)}
out=${OUT_DIR:?OUT_DIR is not set}
playwright=${PLAYWRIGHT_IMAGE:?PLAYWRIGHT_IMAGE is not set}
playwright_version=${PLAYWRIGHT_VERSION:?PLAYWRIGHT_VERSION is not set}
marked_version=${MARKED_VERSION:?MARKED_VERSION is not set}
version=${VERSION:-$(git -C "$repo" describe --tags --abbrev=0)}
date=${DATE:-$(date -u +%Y-%m-%d)}

mkdir -p "$out"
docker run --rm --ipc=host --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -e VERSION="$version" -e DATE="$date" -e OUT=/out/lasteverlm-handbook.pdf \
    -v "$repo:/repo:ro" -v "$out:/out" -v "$here/handbook/build.mjs:/book/build.mjs:ro" \
    "$playwright" sh -c "cp /book/build.mjs /tmp/ && cd /tmp && npm install --silent --no-save --no-audit --no-fund playwright@$playwright_version marked@$marked_version >/dev/null 2>&1 && node build.mjs"
