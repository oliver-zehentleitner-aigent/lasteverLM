# Build context is the repository root: docker build -f ingest/Dockerfile .
# (so that core/ can be copied in once ingest depends on it).
FROM python:3.13-slim AS build
WORKDIR /build
COPY ingest/pyproject.toml ingest/README.md ./ingest/
COPY ingest/src ./ingest/src
RUN pip install --no-cache-dir --prefix=/install ./ingest

FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000
RUN useradd --system --uid 10001 --no-create-home app
COPY --from=build /install /usr/local
USER app
EXPOSE 8000
# API by default; the worker Deployment overrides the command with
# ["lasteverlm-ingest-worker"].
CMD ["sh", "-c", "uvicorn --factory lasteverlm_ingest.main:create_app --host 0.0.0.0 --port ${PORT}"]
