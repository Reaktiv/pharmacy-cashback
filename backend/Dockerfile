FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# libzbar0 is pyzbar's runtime dependency — apps/bot/qr.py decodes receipt
# QR codes via qreader, whose own decode step is pyzbar underneath (see
# that module's docstring for why that's a deliberate, informed choice, not
# an oversight). Unlike the zxing-cpp this replaced, pyzbar ships no
# compiled decoder of its own; it dlopen()s libzbar.so.0 at runtime, so
# without this package the import succeeds but every decode silently fails.
#
# libgl1 and libglib2.0-0 are for opencv-python (requirements.txt pins the
# full build, not -headless — see that file's own comment for why pip can't
# be pointed at -headless here instead). Confirmed via `ldd` on the actual
# installed cv2 .so that these two are the only pieces it resolves from the
# system rather than shipping bundled in the wheel (its Qt5 GUI libs, e.g.,
# are bundled) — without them, `import cv2` fails at runtime with
# "libGL.so.1: cannot open shared object file", not at pip-install time.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev gcc libzbar0 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV PIP_DEFAULT_TIMEOUT=100 \
    PIP_RETRIES=10

COPY requirements.txt .
# --extra-index-url pulls the CPU-only build of torch/torchvision (pinned
# in requirements.txt as *==X.Y.Z+cpu*) instead of the default CUDA wheels,
# which are several GB larger and useless on a server with no GPU. Both
# MUST come from this index together — a CPU torch paired with a
# default-index torchvision (or vice versa) is an ABI mismatch that fails
# at decode time with "RuntimeError: operator torchvision::nms does not
# exist", not at import time, which is why this was easy to miss in
# testing that only imported qreader without ever decoding anything.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

# Bakes qreader's YOLO detection model (~24MB, github.com/Eric-Canas/qrdet
# releases) into the image at build time, so no worker process ever needs
# network access on first receipt-photo decode — see apps/bot/qr.py's
# _get_qreader for why that first decode already happens lazily per
# process. Constructing QReader() is enough to trigger qrdet's own
# download-if-missing check; this doesn't decode anything.
RUN python -c "from qreader import QReader; QReader(model_size='s')"

# Chromium (not firefox/webkit — the smaller single-browser install) is how
# apps/bot/tasks.py reads a fiscal receipt off ofd.soliq.uz: the site's own
# page JS signs its API calls (x-signature/x-timestamp), so a plain HTTP
# request is rejected — only a real rendered page's own request works.
# --with-deps installs the OS-level libraries Chromium needs (fonts,
# libnss3, ...) that this otherwise-minimal image doesn't carry. Run at
# build time, not container start, so the worker never re-downloads it.
RUN playwright install --with-deps chromium

COPY backend/ .
