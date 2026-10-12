# Same targets in every directory of the repository: check, run, build.
# Every target works on a fresh checkout: check and build install first.
.PHONY: install check lint typecheck test run build image

install: node_modules/.package-lock.json

node_modules/.package-lock.json: package.json package-lock.json
	npm ci
	@touch $@

check: install lint typecheck test

lint:
	npm run lint

typecheck:
	npm run typecheck

test:
	npm test

run: install
	npm run dev

build: install
	npm run build

image:
	cd .. && docker build -f web/Dockerfile --build-arg API_BASE_URL="$(API_BASE_URL)" -t lasteverlm-web .
