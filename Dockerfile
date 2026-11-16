# The web interface and the daily pipeline, with headless Chromium for form filling.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HIRELANE_HOME=/data \
    PLAYWRIGHT_BROWSERS_PATH=/opt/browsers

# Playwright's bundled Node needs libatomic, which the slim base image leaves out.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libatomic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY hirelane ./hirelane
RUN pip install ".[web,browser,google]" \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 hirelane \
    && mkdir -p /data \
    && chown hirelane:hirelane /data

USER hirelane
VOLUME /data
EXPOSE 8766

# A container has no OS keyring. Pass secrets as HIRELANE_SECRET_WEB_TOKEN and HIRELANE_SECRET_AI_API_KEY.
# The web interface refuses to listen on a non-loopback address without a token.
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8766/healthz')"
ENTRYPOINT ["hirelane"]
CMD ["web", "--host", "0.0.0.0"]
