# Build context is the repository root: docker build -f ingest/Dockerfile .
# core/ is installed from the same checkout; it is not published.
#
# The base image is pinned by digest (the multi-arch index), so a rebuild of
# the same commit gets the same base. To move to a newer patch release:
#   docker buildx imagetools inspect python:3.13-slim   # "Digest:" line
# and replace the digest below (both stages use it).
ARG PYTHON_IMAGE=python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f
# A minimal ffmpeg for converting recordings the transcription model does
# not take (src/lasteverlm_ingest/loaders/convert.py): only the file
# protocol, the demuxers and decoders of the accepted formats, resampling
# and the MP3 encoder, so the parser surface for uploads stays small and
# the stage adds a few MB instead of Debian's ffmpeg (about 630 MB). Its
# own stage, cached as long as the version and flags stay.
# To bump: take the new version from https://ffmpeg.org/releases/, check
# its .asc with the FFmpeg release signing key (fingerprint FCF9 86EA 15E6
# E293 A564 4F10 B432 2F04 D676 58D8), put its sha256 below.
FROM ${PYTHON_IMAGE} AS ffmpeg
ARG FFMPEG_VERSION=7.1.5
ARG FFMPEG_SHA256=de668509caf9e35e3cd162473441fdb29538c6d96ed080292b3cf9e6fc5d558f
ARG LAME_VERSION=3.100-6+b3
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential pkg-config curl ca-certificates xz-utils \
        libmp3lame-dev=${LAME_VERSION} \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN curl -fsSL -o ffmpeg.tar.xz "https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz" \
    && echo "${FFMPEG_SHA256}  ffmpeg.tar.xz" | sha256sum -c - \
    && tar -xJf ffmpeg.tar.xz --strip-components=1 \
    && ./configure --prefix=/opt/ffmpeg \
        --disable-everything --disable-autodetect --disable-network \
        --disable-doc --disable-debug --disable-ffplay --disable-ffprobe \
        --disable-avdevice --disable-swscale --disable-x86asm \
        --enable-libmp3lame \
        --enable-protocol=file \
        --enable-demuxer=mov,ogg,flac,matroska,aac \
        --enable-parser=aac,flac,opus,vorbis,mpegaudio \
        --enable-decoder=aac,alac,opus,vorbis,flac,mp3 \
        --enable-encoder=libmp3lame --enable-muxer=mp3 \
        --enable-filter=abuffer,abuffersink,aformat,anull,aresample \
    && make -j"$(nproc)" \
    && make install

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
ARG LAME_VERSION=3.100-6+b3
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmp3lame0=${LAME_VERSION} \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --system --uid 10001 --no-create-home app
COPY --from=ffmpeg /opt/ffmpeg/bin/ffmpeg /usr/local/bin/ffmpeg
COPY --from=build /install /usr/local
# Numeric, so that runAsNonRoot can verify it.
USER 10001
EXPOSE 8000
# API by default; the worker Deployment overrides the command with
# ["lasteverlm-ingest-worker"].
CMD ["sh", "-c", "uvicorn --factory lasteverlm_ingest.main:create_app --host 0.0.0.0 --port ${PORT}"]
