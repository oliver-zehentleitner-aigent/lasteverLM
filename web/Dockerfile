# Build the static app, then serve it with nginx as a non-root user.
# Built from the repository root: docker build -f web/Dockerfile .
# API_BASE_URL is baked in at build time; empty means same origin, which is
# the deployed case. Kubernetes probes /healthz, so no HEALTHCHECK here.
FROM node:24-alpine AS build
WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ .
ARG API_BASE_URL=""
ARG VITE_ADMIN_MOCK="false"
ENV API_BASE_URL=$API_BASE_URL VITE_ADMIN_MOCK=$VITE_ADMIN_MOCK
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
USER nginx
EXPOSE 8080
