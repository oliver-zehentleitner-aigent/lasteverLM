#!/bin/sh
# Runs the web image and walks it in headless Chromium against the live API,
# printing every Content Security Policy violation (scripts/csp/walk.mjs).
# Needs Docker and DEMO_TOKEN. WEB_IMAGE: an image to test (default: build one
# from REPO_ROOT with CSP_MODE, report by default, so nothing is blocked and
# every would-be block is listed). API_URL: the deployment (default URL).
set -eu
: "${DEMO_TOKEN:?DEMO_TOKEN is not set}"
: "${API_URL:?API_URL is not set}"
here=$(cd "$(dirname "$0")" && pwd)
repo=${REPO_ROOT:-$(cd "$here/../.." && pwd)}
playwright=${PLAYWRIGHT_IMAGE:?PLAYWRIGHT_IMAGE is not set}
playwright_version=${PLAYWRIGHT_VERSION:?PLAYWRIGHT_VERSION is not set}
run=csp-$(date +%s)

if [ -z "${WEB_IMAGE:-}" ]; then
    WEB_IMAGE=lasteverlm-web:$run
    docker build -q -f "$repo/web/Dockerfile" --build-arg CSP="${CSP_MODE:-report}" -t "$WEB_IMAGE" "$repo" >/dev/null
    built=1
fi

cleanup() {
    docker rm -f "$run-web" >/dev/null 2>&1 || true
    docker network rm "$run" >/dev/null 2>&1 || true
    if [ -n "${built:-}" ]; then docker image rm "$WEB_IMAGE" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT

docker network create "$run" >/dev/null
docker run -d --rm --name "$run-web" --network "$run" --read-only --tmpfs /tmp "$WEB_IMAGE" >/dev/null
docker run --rm --network "$run" --ipc=host \
    -e DEMO_TOKEN -e WEB_URL="http://$run-web:8080" -e API_URL="$API_URL" -e MAX_NOTEBOOKS -e WALK_RPS -e STORAGE_ORIGIN \
    -v "$here/csp/walk.mjs:/walk/walk.mjs:ro" -w /walk "$playwright" \
    sh -c "npm install --silent --no-save --no-audit --no-fund playwright@$playwright_version >/dev/null 2>&1 && node walk.mjs"
