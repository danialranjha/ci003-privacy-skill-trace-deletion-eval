# Minimal native-Codex image for the privacy-skill experiment.
#
# Deliberately ONE client: the paper's privacy-skill condition is a Codex-condition experiment, and
# every extra CLI is build surface and attack surface that this run does not need. Node comes from
# the official image rather than apt so the codex runtime version is pinned the same way upstream
# pins it.
FROM node:22.22.0-bookworm-slim AS node_runtime
FROM python:3.12-slim-bookworm

ARG CODEX_VERSION=0.154.0

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git ripgrep procps \
    && rm -rf /var/lib/apt/lists/*

COPY --from=node_runtime /usr/local/ /usr/local/

RUN npm install --global "@openai/codex@${CODEX_VERSION}" \
    && codex --version

RUN useradd --create-home --uid 1000 --shell /bin/bash agent \
    && mkdir -p /workspace /relay \
    && chown -R 1000:1000 /workspace /relay /home/agent

COPY lab /opt/lab/lab
COPY assets /opt/lab/assets

# HOME is explicit: Docker does not derive it from /etc/passwd for a non-root USER, and Codex
# writes its session transcript under $HOME/.codex/sessions. A wrong HOME would silently move the
# trace the experiment is about.
ENV HOME=/home/agent \
    PYTHONPATH=/opt/lab \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /workspace
USER agent
CMD ["python3", "-m", "lab.relay"]
