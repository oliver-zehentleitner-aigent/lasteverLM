FROM python:3.13-slim AS build
WORKDIR /app
# Build context is the repository root: docker build -f account/Dockerfile .
COPY core ./core
COPY account ./account
RUN pip install --no-cache-dir --prefix=/install ./core ./account

FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000
RUN useradd --system --uid 10001 --no-create-home app
COPY --from=build /install /usr/local
USER 10001
EXPOSE 8000
CMD ["sh", "-c", "uvicorn --factory lasteverlm_account.main:create_app --host 0.0.0.0 --port ${PORT}"]
