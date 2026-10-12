# Built with the repository root as context: docker build -f rag/Dockerfile .
# Build stage: resolve and install into a self-contained virtualenv.
FROM python:3.13-slim AS build
WORKDIR /src
COPY rag/pyproject.toml rag/README.md ./
COPY rag/lasteverlm_rag ./lasteverlm_rag
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir .

# Runtime stage: only the virtualenv, no build tooling, non-root.
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH"
COPY --from=build /opt/venv /opt/venv
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
CMD ["uvicorn", "lasteverlm_rag.main:app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
