# Built with the repository root as context, so core/ can be copied in:
#   docker build -f rag/Dockerfile .
# The base image is pinned by its multi-arch index digest, so a rebuild gets
# the same bytes. To refresh: `docker buildx imagetools inspect python:3.13-slim`
# and copy the top-level "Digest:" here.
ARG PYTHON_IMAGE=python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f
FROM ${PYTHON_IMAGE} AS build
WORKDIR /app
COPY core ./core
COPY rag ./rag
RUN pip install --no-cache-dir --prefix=/install ./core ./rag

FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=build /install /usr/local
RUN useradd --create-home --uid 10001 app
USER 10001
EXPOSE 8000
CMD ["uvicorn", "lasteverlm_rag.main:app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
