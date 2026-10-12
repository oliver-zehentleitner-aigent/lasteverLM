# Built with the repository root as context, so core/ can be copied in:
#   docker build -f rag/Dockerfile .
FROM python:3.13-slim AS build
WORKDIR /app
COPY core ./core
COPY rag ./rag
RUN pip install --no-cache-dir --prefix=/install ./core ./rag

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=build /install /usr/local
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
CMD ["uvicorn", "lasteverlm_rag.main:app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
