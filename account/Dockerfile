# Base image pinned by digest (the multi-arch index, so the pin holds on every platform);
# the tag stays for readability. Refresh both FROM lines with:
#   docker buildx imagetools inspect python:3.13-slim   # copy the top-level "Digest:"
FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f AS build
WORKDIR /app
# Build context is the repository root: docker build -f account/Dockerfile .
COPY core ./core
COPY account ./account
RUN pip install --no-cache-dir --prefix=/install ./core ./account

FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000
RUN useradd --system --uid 10001 --no-create-home app
COPY --from=build /install /usr/local
USER 10001
EXPOSE 8000
CMD ["sh", "-c", "uvicorn --factory lasteverlm_account.main:create_app --host 0.0.0.0 --port ${PORT}"]
