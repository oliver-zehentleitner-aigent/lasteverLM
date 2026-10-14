# lasteverLM infra: from a clean checkout to a running cluster.
# Run from this directory. Every target is idempotent; README.md shows the order.
.RECIPEPREFIX = >
.DEFAULT_GOAL := help
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

BUILD       := $(CURDIR)/build
TOFU_DIR    := $(CURDIR)/tofu
CHART       := $(CURDIR)/chart
KUBE_NS     := lasteverlm
RELEASE     := lasteverlm
CLUSTER_ENV := $(BUILD)/cluster.env
REPO_ROOT   := $(abspath $(CURDIR)/..)

# Image registry and tag. The release workflow passes the Git tag; locally
# TAG defaults to latest. One tag for every service: the repository is one.
REGISTRY ?= ghcr.io/oliver-zehentleitner
TAG      ?= latest
# The checked-out commit, reported as APP_COMMIT. deploy.yml checks out the
# commit the images were built from; on an operator machine, check out TAG first.
COMMIT   ?= $(shell git -C $(REPO_ROOT) rev-parse HEAD 2>/dev/null)

# The deployment's non-secret configuration (domain, models, prices, S3
# endpoint), committed. Another deployment passes its own file.
VALUES ?= $(CHART)/values-prod.yaml
DOMAIN_FROM_VALUES = $(shell sed -n 's/^domain: *//p' $(VALUES))
URL ?= $(if $(DOMAIN_FROM_VALUES),https://$(DOMAIN_FROM_VALUES))

# Services whose db/migrations/ are applied after this directory's own, in
# this order (see db/migrate.sh). Sibling directories in the mono repo.
MIGRATION_SERVICES := core account ingest rag

# Platform charts, pinned. Bump deliberately, note it in CHANGELOG.md.
INGRESS_NGINX_CHART  := 4.15.1
CERT_MANAGER_CHART   := v1.21.2
METRICS_SERVER_CHART := 3.14.0

export KUBECONFIG := $(BUILD)/kubeconfig

# $(call require,VAR) fails loud when VAR is unset or empty.
require = $(if $(strip $($(1))),,$(error $(1) is not set))

.PHONY: tag-check help up vke-versions env kubeconfig bucket platform secrets db-trust db-bootstrap migrations deploy package status down check test smoke web-csp-check local-up local-down local-reset local-smoke

help: ## list targets
> @grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | column -t -s $$'\t'

# Vultr resources ----------------------------------------------------------------

up: ## create or update cluster and object storage (needs VULTR_API_KEY; AUTO_APPROVE=1 skips the plan prompt)
> $(call require,VULTR_API_KEY)
> @test -f $(TOFU_DIR)/terraform.tfvars || test -n "$${TF_VAR_object_storage_tier_id:-}" || { echo "set TF_VAR_object_storage_tier_id or copy tofu/terraform.tfvars.example to tofu/terraform.tfvars" >&2; exit 1; }
> cd $(TOFU_DIR) && tofu init -input=false && tofu apply -input=false $(if $(AUTO_APPROVE),-auto-approve); status=$$?; chmod 600 terraform.tfstate*; exit $$status
> $(MAKE) --no-print-directory env

vke-versions: ## list VKE versions the API offers right now
> @curl -fsS https://api.vultr.com/v2/kubernetes/versions

# keep <VAR> from the previous cluster.env, or generate it once (never printed)
keep_or_gen = $$( { grep -s '^$(1)=' $(CLUSTER_ENV) | cut -d= -f2-; } || true); [ -n "$$$(2)" ] || $(2)=$$(openssl rand -base64 48 | tr -d '/+=\n' | cut -c1-$(3))
# the same for a key of <bytes> random bytes in standard base64 with padding
keep_or_gen_key = $$( { grep -s '^$(1)=' $(CLUSTER_ENV) | cut -d= -f2-; } || true); [ -n "$$$(2)" ] || $(2)=$$(openssl rand -base64 $(3))

env: ## write build/cluster.env: tofu outputs, derived database URLs, generated secrets (ignored by Git, never printed)
> $(call require,DATABASE_ADMIN_URL)
> @mkdir -p $(BUILD) && umask 077 && \
>   pw=$(call keep_or_gen,APP_DB_PASSWORD,pw,32); jwt=$(call keep_or_gen,AUTH_JWT_SECRET,jwt,64); demo=$(call keep_or_gen,DEMO_TOKEN,demo,48); \
>   vk=$(call keep_or_gen_key,VOUCHER_KEY,vk,32); \
>   outs=$$(cd $(TOFU_DIR) && tofu output -json | python3 $(CURDIR)/scripts/tofu_outputs.py) && \
>   urls=$$(APP_DB_PASSWORD=$$pw python3 $(CURDIR)/scripts/dburls.py) && { \
>   echo "APP_DB_PASSWORD=$$pw"; echo "AUTH_JWT_SECRET=$$jwt"; echo "DEMO_TOKEN=$$demo"; echo "VOUCHER_KEY=$$vk"; \
>   echo "$$urls"; echo "$$outs"; \
> } > $(CLUSTER_ENV) && echo "wrote $(CLUSTER_ENV)"

$(CLUSTER_ENV):
> $(MAKE) --no-print-directory env

kubeconfig: $(CLUSTER_ENV) ## fetch the kubeconfig into build/kubeconfig (needs VULTR_API_KEY)
> $(call require,VULTR_API_KEY)
> @umask 077 && . $(CLUSTER_ENV) && vultr-cli kubernetes config "$$VKE_ID" | base64 -d > $(KUBECONFIG)
> kubectl cluster-info

# Note: make keeps the recipe prefix when a backslash-newline falls inside a
# shell $(...) substitution, so every $$(...) below stays on one line.
bucket: $(CLUSTER_ENV) ## create the sources bucket (one signed S3 PUT; 200 or 409 both mean it exists; private by default)
> @. $(CLUSTER_ENV) && \
>   code=$$(curl -sS -o /dev/null -w '%{http_code}' -X PUT --aws-sigv4 "aws:amz:$$S3_REGION:s3" --user "$$S3_ACCESS_KEY:$$S3_SECRET_KEY" "$$S3_ENDPOINT/$$S3_BUCKET") && \
>   case "$$code" in 200|409) echo "bucket $$S3_BUCKET ok ($$code)";; *) echo "bucket creation failed: HTTP $$code" >&2; exit 1;; esac

# Cluster --------------------------------------------------------------------------

platform: ## ingress-nginx (JSON access log, PROXY protocol), cert-manager, metrics-server; pinned chart versions
> $(call require,DOMAIN_FROM_VALUES)
> helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx >/dev/null 2>&1 || true
> helm repo add jetstack https://charts.jetstack.io >/dev/null 2>&1 || true
> helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/ >/dev/null 2>&1 || true
> helm repo update >/dev/null
> helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx --version $(INGRESS_NGINX_CHART) \
>   -n ingress-nginx --create-namespace -f platform/ingress-nginx.values.yaml --wait --timeout 5m \
>   --set-string 'controller.service.annotations.service\.beta\.kubernetes\.io/vultr-loadbalancer-hostname=$(DOMAIN_FROM_VALUES)'
> helm upgrade --install cert-manager jetstack/cert-manager --version $(CERT_MANAGER_CHART) \
>   -n cert-manager --create-namespace -f platform/cert-manager.values.yaml --wait --timeout 5m
> helm upgrade --install metrics-server metrics-server/metrics-server --version $(METRICS_SERVER_CHART) \
>   -n kube-system -f platform/metrics-server.values.yaml --wait --timeout 5m
> @echo "load balancer id (vultr-cli load-balancer get <id> shows the IP to point the domain at):" && kubectl -n ingress-nginx get svc ingress-nginx-controller -o jsonpath='{.metadata.annotations.service\.beta\.kubernetes\.io/vultr-loadbalancer-id}{"\n"}'

secrets: env ## create the Secrets and the CA ConfigMap from cluster.env and the environment; re-run after a password rotation
> $(call require,INFERENCE_API_KEY)
> $(call require,PGSSLROOTCERT)
> @kubectl get namespace $(KUBE_NS) >/dev/null 2>&1 || kubectl create namespace $(KUBE_NS)
> @kubectl -n $(KUBE_NS) create configmap lasteverlm-pg-ca --from-file=pg-ca.crt=$(PGSSLROOTCERT) --dry-run=client -o yaml | kubectl apply -f -
> @. $(CLUSTER_ENV) && \
>   kubectl -n $(KUBE_NS) create secret generic lasteverlm-db --from-literal=DATABASE_URL="$$DATABASE_URL" --dry-run=client -o yaml | kubectl apply -f - && \
>   kubectl -n $(KUBE_NS) create secret generic lasteverlm-db-admin --from-literal=DATABASE_URL="$$DATABASE_ADMIN_APP_URL" --dry-run=client -o yaml | kubectl apply -f - && \
>   kubectl -n $(KUBE_NS) create secret generic lasteverlm-s3 --from-literal=S3_ACCESS_KEY="$$S3_ACCESS_KEY" --from-literal=S3_SECRET_KEY="$$S3_SECRET_KEY" --dry-run=client -o yaml | kubectl apply -f - && \
>   kubectl -n $(KUBE_NS) create secret generic lasteverlm-inference --from-literal=INFERENCE_API_KEY="$$INFERENCE_API_KEY" --dry-run=client -o yaml | kubectl apply -f - && \
>   kubectl -n $(KUBE_NS) create secret generic lasteverlm-auth --from-literal=AUTH_JWT_SECRET="$$AUTH_JWT_SECRET" --from-literal=DEMO_TOKEN="$$DEMO_TOKEN" --dry-run=client -o yaml | kubectl apply -f - && \
>   kubectl -n $(KUBE_NS) create secret generic lasteverlm-account --from-literal=AUTH_ALLOWED_DOMAINS="$${AUTH_ALLOWED_DOMAINS:-}" --from-literal=ADMIN_EMAILS="$${ADMIN_EMAILS:-}" --from-literal=VISIT_HASH_SECRET="$${VISIT_HASH_SECRET:-}" --from-literal=VOUCHER_KEY="$$VOUCHER_KEY" --from-literal=VULTR_BILLING_API_KEY="$${VULTR_BILLING_API_KEY:-}" --dry-run=client -o yaml | kubectl apply -f -
> @if [ -n "$${SMTP_HOST:-}" ]; then \
>   [ -n "$${SMTP_FROM_ADDRESS:-}" ] || { echo "SMTP_HOST is set but SMTP_FROM_ADDRESS is not; account refuses to start without it" >&2; exit 1; }; \
>   kubectl -n $(KUBE_NS) create secret generic lasteverlm-smtp \
>     --from-literal=SMTP_HOST="$$SMTP_HOST" --from-literal=SMTP_PORT="$${SMTP_PORT:-587}" \
>     --from-literal=SMTP_USERNAME="$${SMTP_USERNAME:-}" --from-literal=SMTP_PASSWORD="$${SMTP_PASSWORD:-}" \
>     --from-literal=SMTP_FROM_ADDRESS="$$SMTP_FROM_ADDRESS" --from-literal=SMTP_STARTTLS="$${SMTP_STARTTLS:-true}" \
>     --dry-run=client -o yaml | kubectl apply -f -; \
> else echo "SMTP_HOST not set, no lasteverlm-smtp secret (optional)"; fi

db-trust: ## allow only the cluster nodes (IPv4; the API accepts no IPv6 yet) and this machine on the managed database; re-run after node changes
> $(call require,VULTR_API_KEY)
> @nodes=$$(kubectl get nodes -o jsonpath='{.items[*].status.addresses[?(@.type=="ExternalIP")].address}' | tr ' ' '\n' | grep -E '^[0-9.]+$$' | paste -sd,); \
>   me=$$(curl -fsS https://api4.ipify.org); \
>   id=$$(curl -fsS -H "Authorization: Bearer $$VULTR_API_KEY" https://api.vultr.com/v2/databases | python3 -c 'import sys,json; print(next(d["id"] for d in json.load(sys.stdin)["databases"] if d["database_engine"]=="pg"))'); \
>   vultr-cli database update "$$id" --trusted-ips "$$nodes,$$me" >/dev/null && echo "trusted ips: $$nodes,$$me"

db-bootstrap: secrets ## one-time: application role, database and pgvector on the managed instance (Job, admin role)
> @. $(CLUSTER_ENV) && kubectl -n $(KUBE_NS) create secret generic lasteverlm-db-bootstrap \
>   --from-literal=DATABASE_ADMIN_URL="$$DATABASE_ADMIN_URL" --from-literal=APP_DB_PASSWORD="$$APP_DB_PASSWORD" \
>   --dry-run=client -o yaml | kubectl apply -f -
> kubectl -n $(KUBE_NS) create configmap lasteverlm-db-bootstrap --from-file=db/bootstrap.sh --dry-run=client -o yaml | kubectl apply -f -
> @mkdir -p $(BUILD) && run=$$(date -u +%Y%m%d%H%M%S) && sed "s/__RUN_ID__/$$run/g" db/bootstrap-job.yaml > $(BUILD)/bootstrap-job.yaml && \
>   kubectl apply -f $(BUILD)/bootstrap-job.yaml && \
>   { kubectl -n $(KUBE_NS) wait --for=condition=complete --timeout=300s job/db-bootstrap-$$run || status=$$?; }; \
>   kubectl -n $(KUBE_NS) logs job/db-bootstrap-$$run; exit $${status:-0}

migrations: ## collect infra + every service's db/migrations/ into chart/files/migrations.tgz
> @rm -rf $(BUILD)/migrations && mkdir -p $(BUILD)/migrations/infra && cp db/migrations/*.sql $(BUILD)/migrations/infra/
> @for s in $(MIGRATION_SERVICES); do \
>   dest=$(BUILD)/migrations/$$s; mkdir -p $$dest; src=$(REPO_ROOT)/$$s/db/migrations; \
>   if [ -d $$src ] && ls $$src/*.sql >/dev/null 2>&1; then cp $$src/*.sql $$dest/; else echo "note: no migrations in $$src"; fi; \
>   echo "$$s: $$(ls $$dest | tr '\n' ' ')"; \
> done
> @tar czf $(CHART)/files/migrations.tgz -C $(BUILD)/migrations . && cp db/migrate.sh $(CHART)/files/migrate.sh && echo "wrote chart/files/migrations.tgz"

tag-check: ## refuse a short commit SHA as TAG (images carry the full SHA)
> @if [[ "$(TAG)" =~ ^[0-9a-f]{7,39}$$ ]]; then echo "TAG=$(TAG) looks like a short commit SHA; docker.yml tags images with the full 40-character SHA" >&2; exit 1; fi

deploy: tag-check migrations ## helm upgrade --install of the chart with VALUES: migrations hook, then every service at TAG (HELM_WAIT=0 returns without waiting)
> $(call require,COMMIT)
> helm upgrade --install $(RELEASE) $(CHART) -n $(KUBE_NS) --create-namespace -f $(VALUES) \
>   --set registry=$(REGISTRY) --set-string imageTag=$(TAG) \
>   --set-string appVersion=$(TAG) --set-string appCommit=$(COMMIT) $(if $(filter 0,$(HELM_WAIT)),,--wait --timeout 10m)
> kubectl -n $(KUBE_NS) get deployments,hpa

package: migrations ## package the chart: make package VERSION=0.1.0 (from the tag v0.1.0)
> $(call require,VERSION)
> helm package $(CHART) --version $(VERSION) --app-version $(VERSION) -d $(BUILD)

status: ## what is running
> kubectl -n $(KUBE_NS) get deployments,hpa,pods,ingress,certificate

down: ## destroy every Vultr resource (asks first)
> $(call require,VULTR_API_KEY)
> cd $(TOFU_DIR) && tofu destroy -input=false
> rm -f $(CLUSTER_ENV) $(KUBECONFIG)

# Checks ---------------------------------------------------------------------------

check: test ## static checks and unit tests: tofu, helm lint + template with VALUES, shell syntax, black, tests, ktw-lint
> cd $(TOFU_DIR) && tofu fmt -check -recursive && tofu init -backend=false -input=false >/dev/null && VULTR_API_KEY=$${VULTR_API_KEY:-validate-only} tofu validate
> helm lint $(CHART) -f $(VALUES) >/dev/null && helm template check $(CHART) -f $(VALUES) >/dev/null && echo "helm ok"
> sh -n db/migrate.sh && sh -n db/bootstrap.sh && echo "migrate.sh + bootstrap.sh ok"
> black --check --quiet scripts tests && echo "black ok"
> DATABASE_ADMIN_URL='postgresql://a:b@h:1/defaultdb?sslmode=require' APP_DB_PASSWORD=x python3 scripts/dburls.py >/dev/null && echo "dburls.py ok"
> @if command -v ktw-lint >/dev/null; then ktw-lint .; else echo "ktw-lint not installed, skipped (pipx install keep-the-why-lint)"; fi

test: ## unit tests (the smoke test against an in-process stub)
> python3 -m unittest discover -s tests

# Headless Chromium for web-csp-check, pinned by digest; the npm package matches the image.
PLAYWRIGHT_VERSION := 1.63.0
PLAYWRIGHT_IMAGE   := mcr.microsoft.com/playwright:v$(PLAYWRIGHT_VERSION)-noble@sha256:eff16c30e6f3f4af0a03fa4b706120d5e9b0891c344a27d64559aff5900a4a27

web-csp-check: ## walk the web image in headless Chromium against URL, list every CSP violation (Docker, DEMO_TOKEN; WEB_IMAGE=<image> or a build with CSP_MODE=report)
> $(call require,URL)
> $(call require,DEMO_TOKEN)
> API_URL=$(URL) REPO_ROOT=$(REPO_ROOT) PLAYWRIGHT_IMAGE=$(PLAYWRIGHT_IMAGE) PLAYWRIGHT_VERSION=$(PLAYWRIGHT_VERSION) sh scripts/web-csp-check.sh

smoke: ## end-to-end smoke test against URL (default https://<domain in VALUES>; token from DEMO_TOKEN; SMOKE_ARGS="--host d --insecure" before DNS exists)
> $(call require,URL)
> $(call require,DEMO_TOKEN)
> python3 tests/smoke.py $(URL) $(SMOKE_ARGS)

# Local development (compose.yaml) ------------------------------------------------

COMPOSE := docker compose -f $(CURDIR)/compose.yaml

local-up: ## local stack: Postgres+pgvector, S3 storage, Mailpit, every service, gateway on 127.0.0.1:8080 (needs INFERENCE_API_KEY)
> $(call require,INFERENCE_API_KEY)
> $(COMPOSE) up --build -d --wait
> @echo "app http://localhost:8080  mail http://localhost:8025  storage console http://localhost:9001"

local-down: ## stop the local stack, keep its data
> $(COMPOSE) down

local-reset: ## stop the local stack and delete its database and storage volumes
> $(COMPOSE) down --volumes

local-smoke: ## end-to-end smoke test against the local stack
> DEMO_TOKEN=$${DEMO_TOKEN:-local-demo-token} python3 tests/smoke.py http://localhost:$${GATEWAY_PORT:-8080} --ready-timeout 300
