# Build context is the repository root: docker build -f ingest/Dockerfile .
# core/ is installed from the same checkout; it is not published.
#
# The base image is pinned by digest (the multi-arch index), so a rebuild of
# the same commit gets the same base. To move to a newer patch release:
#   docker buildx imagetools inspect python:3.13-slim   # "Digest:" line
# and replace the digest below (both stages use it).
ARG PYTHON_IMAGE=python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f
FROM ${PYTHON_IMAGE} AS build
WORKDIR /build
COPY core ./core
COPY ingest/pyproject.toml ingest/README.md ./ingest/
COPY ingest/src ./ingest/src
RUN pip install --no-cache-dir --prefix=/install ./core ./ingest

FROM ${PYTHON_IMAGE}
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000
RUN useradd --system --uid 10001 --no-create-home app
COPY --from=build /install /usr/local
# Numeric, so that runAsNonRoot can verify it.
USER 10001
EXPOSE 8000
# API by default; the worker Deployment overrides the command with
# ["lasteverlm-ingest-worker"].
CMD ["sh", "-c", "uvicorn --factory lasteverlm_ingest.main:create_app --host 0.0.0.0 --port ${PORT}"]
