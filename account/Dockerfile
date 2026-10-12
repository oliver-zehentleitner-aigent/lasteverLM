FROM python:3.13-slim AS build
WORKDIR /app
# Build context is the repository root: docker build -f account/Dockerfile .
COPY account/pyproject.toml account/README.md ./
COPY account/src ./src
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000
RUN useradd --system --uid 10001 --no-create-home app
COPY --from=build /install /usr/local
USER app
EXPOSE 8000
CMD ["sh", "-c", "uvicorn lasteverlm_account.main:app --host 0.0.0.0 --port ${PORT}"]
