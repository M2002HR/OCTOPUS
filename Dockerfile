FROM python:3.12-slim

WORKDIR /app

ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG ALL_PROXY=""
ARG NO_PROXY=""
ARG PIP_INDEX_URL=""
ARG PIP_EXTRA_INDEX_URL=""

RUN HTTP_PROXY="${HTTP_PROXY}" HTTPS_PROXY="${HTTPS_PROXY}" ALL_PROXY="${ALL_PROXY}" NO_PROXY="${NO_PROXY}" apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY scripts/container_entrypoint.py scripts/media_overlay_stun_probe.py /app/scripts/
RUN if [ -n "${PIP_INDEX_URL}" ]; then pip config set global.index-url "${PIP_INDEX_URL}"; fi \
    && if [ -n "${PIP_EXTRA_INDEX_URL}" ]; then pip config set global.extra-index-url "${PIP_EXTRA_INDEX_URL}"; fi \
    && HTTP_PROXY="${HTTP_PROXY}" HTTPS_PROXY="${HTTPS_PROXY}" ALL_PROXY="${ALL_PROXY}" NO_PROXY="${NO_PROXY}" pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 voiceagent

ENTRYPOINT ["python", "/app/scripts/container_entrypoint.py"]
