FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# libzbar0 decodes the QR code on a customer's receipt photo (pyzbar).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev gcc libzbar0 \
    && rm -rf /var/lib/apt/lists/*

ENV PIP_DEFAULT_TIMEOUT=100 \
    PIP_RETRIES=10

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Chromium (not firefox/webkit — the smaller single-browser install) is how
# apps/bot/tasks.py reads a fiscal receipt off ofd.soliq.uz: the site's own
# page JS signs its API calls (x-signature/x-timestamp), so a plain HTTP
# request is rejected — only a real rendered page's own request works.
# --with-deps installs the OS-level libraries Chromium needs (fonts,
# libnss3, ...) that this otherwise-minimal image doesn't carry. Run at
# build time, not container start, so the worker never re-downloads it.
RUN playwright install --with-deps chromium

COPY backend/ .
