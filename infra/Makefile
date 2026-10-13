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

.PHONY: tag-check help up vke-versions env kubeconfig bucket platform secrets db-trust db-bootstrap migrations values deploy package status down check test smoke local-up local-down local-reset local-smoke

help: ## list targets
> @grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | column -t -s $$'\t'

# Vultr resources ----------------------------------------------------------------

up: ## create or update cluster and object storage (needs VULTR_API_KEY; AUTO_APPROVE=1 skips the plan prompt)
> $(call require,VULTR_API_KEY)
> @test -f $(TOFU_DIR)/terraform.tfvars || test -n "$${TF_VAR_object_storage_tier_id:-}" || { echo "set TF_VAR_object_storage_tier_id or copy tofu/terraform.tfvars.example to tofu/terraform.tfvars" >&2; exit 1; }
> cd $(TOFU_DIR) && tofu init -input=false && tofu apply -input=false $(if $(AUTO_APPROVE),-auto-approve)
> $(MAKE) --no-print-directory env

vke-versions: ## list VKE versions the API offers right now
> @curl -fsS https://api.vultr.com/v2/kubernetes/versions

# keep <VAR> from the previous cluster.env, or generate it once (never printed)
keep_or_gen = $$( { grep -s '^$(1)=' $(CLUSTER_ENV) | cut -d= -f2-; } || true); [ -n "$$$(2)" ] || $(2)=$$(openssl rand -base64 48 | tr -d '/+=\n' | cut -c1-$(3))

env: ## write build/cluster.env: tofu outputs, derived database URLs, generated secrets (ignored by Git, never printed)
> $(call require,DATABASE_ADMIN_URL)
> @mkdir -p $(BUILD) && umask 077 && \
>   pw=$(call keep_or_gen,APP_DB_PASSWORD,pw,32); jwt=$(call keep_or_gen,AUTH_JWT_SECRET,jwt,64); demo=$(call keep_or_gen,DEMO_TOKEN,demo,48); \
>   cd $(TOFU_DIR) && { \
>   echo "VKE_ID=$$(tofu output -raw vke_id)"; \
>   echo "APP_DB_PASSWORD=$$pw"; echo "AUTH_JWT_SECRET=$$jwt"; echo "DEMO_TOKEN=$$demo"; \
>   APP_DB_PASSWORD=$$pw python3 $(CURDIR)/scripts/dburls.py; \
>   echo "S3_ENDPOINT=$$(tofu output -raw s3_endpoint)"; \
>   echo "S3_BUCKET=$$(tofu output -raw s3_bucket)"; \
>   echo "S3_REGION=$$(tofu output -raw s3_region)"; \
>   echo "S3_ACCESS_KEY=$$(tofu output -raw s3_access_key)"; \
>   echo "S3_SECRET_KEY=$$(tofu output -raw s3_secret_key)"; \
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

platform: ## ingress-nginx (JSON access log), cert-manager, metrics-server; pinned chart versions
> helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx >/dev/null 2>&1 || true
> helm repo add jetstack https://charts.jetstack.io >/dev/null 2>&1 || true
> helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/ >/dev/null 2>&1 || true
> helm repo update >/dev/null
> helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx --version $(INGRESS_NGINX_CHART) \
>   -n ingress-nginx --create-namespace -f platform/ingress-nginx.values.yaml --wait --timeout 5m
> helm upgrade --install cert-manager jetstack/cert-manager --version $(CERT_MANAGER_CHART) \
>   -n cert-manager --create-namespace -f platform/cert-manager.values.yaml --wait --timeout 5m
> helm upgrade --install metrics-server metrics-server/metrics-server --version $(METRICS_SERVER_CHART) \
>   -n kube-system -f platform/metrics-server.values.yaml --wait --timeout 5m
> @echo "ingress IP (point DOMAIN at it):" && kubectl -n ingress-nginx get svc ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}{"\n"}'

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
>   kubectl -n $(KUBE_NS) create secret generic lasteverlm-account --from-literal=AUTH_ALLOWED_DOMAINS="$${AUTH_ALLOWED_DOMAINS:-}" --from-literal=ADMIN_EMAILS="$${ADMIN_EMAILS:-}" --from-literal=VISIT_HASH_SECRET="$${VISIT_HASH_SECRET:-}" --dry-run=client -o yaml | kubectl apply -f -
> @if [ -n "$${SMTP_HOST:-}" ]; then \
>   kubectl -n $(KUBE_NS) create secret generic lasteverlm-smtp-seed \
>     --from-literal=SMTP_HOST="$$SMTP_HOST" --from-literal=SMTP_PORT="$${SMTP_PORT:-587}" \
>     --from-literal=SMTP_USER="$${SMTP_USER:-}" --from-literal=SMTP_PASSWORD="$${SMTP_PASSWORD:-}" \
>     --from-literal=SMTP_FROM="$${SMTP_FROM:-}" --dry-run=client -o yaml | kubectl apply -f -; \
> else echo "SMTP_HOST not set, no lasteverlm-smtp-seed secret (optional)"; fi

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

values: ## write build/values.yaml for the chart from the environment (plus build/cluster.env when present)
> $(call require,DOMAIN)
> $(call require,ACME_EMAIL)
> $(call require,LLM_MODEL)
> $(call require,EMBEDDING_MODEL)
> $(call require,MODEL_PRICES)
> @mkdir -p $(BUILD); if [ -f $(CLUSTER_ENV) ]; then set -a; . $(CLUSTER_ENV); set +a; fi; \
>   REGISTRY=$(REGISTRY) TAG=$(TAG) DOMAIN=$(DOMAIN) ACME_EMAIL=$(ACME_EMAIL) \
>   python3 scripts/values.py > $(BUILD)/values.yaml && echo "wrote $(BUILD)/values.yaml"

tag-check: ## refuse a short commit SHA as TAG (images carry the full SHA)
> @if [[ "$(TAG)" =~ ^[0-9a-f]{7,39}$$ ]]; then echo "TAG=$(TAG) looks like a short commit SHA; docker.yml tags images with the full 40-character SHA" >&2; exit 1; fi

deploy: tag-check values migrations ## helm upgrade --install of the chart: migrations hook, then every service at TAG (HELM_WAIT=0 returns without waiting)
> helm upgrade --install $(RELEASE) $(CHART) -n $(KUBE_NS) --create-namespace -f $(BUILD)/values.yaml $(if $(filter 0,$(HELM_WAIT)),,--wait --timeout 10m)
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

LINT_SET := --set domain=example.test --set acmeEmail=ops@example.test --set config.llmModel=m \
  --set config.embeddingModel=e --set-string config.modelPrices='{}' --set config.s3Endpoint=https://s3.example.test

check: test ## static checks and unit tests: tofu, helm lint + template, shell syntax, black, tests, ktw-lint
> cd $(TOFU_DIR) && tofu fmt -check -recursive && tofu init -backend=false -input=false >/dev/null && VULTR_API_KEY=$${VULTR_API_KEY:-validate-only} tofu validate
> helm lint $(CHART) $(LINT_SET) >/dev/null && helm template check $(CHART) $(LINT_SET) >/dev/null && echo "helm ok"
> sh -n db/migrate.sh && sh -n db/bootstrap.sh && echo "migrate.sh + bootstrap.sh ok"
> black --check --quiet scripts tests && echo "black ok"
> DATABASE_ADMIN_URL='postgresql://a:b@h:1/defaultdb?sslmode=require' APP_DB_PASSWORD=x python3 scripts/dburls.py >/dev/null && echo "dburls.py ok"
> DOMAIN=d ACME_EMAIL=e LLM_MODEL=l EMBEDDING_MODEL=m MODEL_PRICES='{"m":{"in":1,"out":2}}' S3_ENDPOINT=https://s3 python3 scripts/values.py >/dev/null && echo "values.py ok"
> @if command -v ktw-lint >/dev/null; then ktw-lint .; else echo "ktw-lint not installed, skipped (pipx install keep-the-why-lint)"; fi

test: ## unit tests (the smoke test against an in-process stub)
> python3 -m unittest discover -s tests

smoke: ## end-to-end smoke test: make smoke URL=https://... (token from DEMO_TOKEN; SMOKE_ARGS="--host d --insecure" before DNS exists)
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
