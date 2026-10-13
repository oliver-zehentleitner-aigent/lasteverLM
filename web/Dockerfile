# Build the static app, then serve it with nginx as a non-root user.
# Built from the repository root: docker build -f web/Dockerfile .
# API_BASE_URL is baked in at build time; empty means same origin, which is
# the deployed case. Kubernetes probes /healthz, so no HEALTHCHECK here.
# Base images pinned by digest (the multi-arch index), the tag kept for
# reading. To refresh: docker pull <image>:<tag>, then
# docker image inspect --format '{{index .RepoDigests 0}}' <image>:<tag>
# and replace the digest; rebuild and rerun the CSP check (infra: make web-csp-check).
FROM node:24-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1 AS build
WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ .
ARG API_BASE_URL=""
ARG VITE_ADMIN_MOCK="false"
ENV API_BASE_URL=$API_BASE_URL VITE_ADMIN_MOCK=$VITE_ADMIN_MOCK
RUN npm run build
# CSP: enforce (the default), report (full policy, Report-Only) or off
# (frame-ancestors only); the inline script's hash comes from this build's index.html
ARG CSP="enforce"
ARG CSP_MEDIA_SRC="https:"
RUN node scripts/csp.mjs dist/index.html "$CSP" "$CSP_MEDIA_SRC" > /app/csp.conf

FROM nginxinc/nginx-unprivileged:1.29-alpine@sha256:0c79d56aee561a1d81c63f00eee5fb5fe29279560cdc55e91425133104c7fbe6
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY web/security-headers.conf /etc/nginx/security-headers.conf
COPY --from=build /app/csp.conf /etc/nginx/csp.conf
COPY --from=build /app/dist /usr/share/nginx/html
# numeric so that Kubernetes runAsNonRoot can verify it (a name cannot be checked)
USER 101
EXPOSE 8080
