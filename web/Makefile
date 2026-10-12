# Same targets in every repository of the family: check, run, build.
.PHONY: check lint typecheck test run build image

check: lint typecheck test

lint:
	npm run lint

typecheck:
	npm run typecheck

test:
	npm test

run:
	npm run dev

build:
	npm run build

image:
	cd .. && docker build -f web/Dockerfile --build-arg API_BASE_URL="$(API_BASE_URL)" -t lasteverlm-web .
