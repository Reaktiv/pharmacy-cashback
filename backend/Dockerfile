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
# No GUI/X11 packages needed here: requirements.txt pins opencv-python-
# headless specifically so this image never needs them — see that file's
# own comment for why (the plain opencv-python/Qt5 build was tried first
# and rejected after chasing libGL, then libxcb, then libSM/libICE one
# ldd-and-rebuild cycle at a time; -headless needs nothing beyond what
# this base image already has, confirmed via `ldd` with zero "not found"
# lines on the actual installed cv2 .so).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev gcc libzbar0 \
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

# ultralytics, qrdet and qreader are deliberately NOT in requirements.txt
# and installed here instead, with --no-deps: all three hard-require the
# package name "opencv-python" (the GUI/Qt5 build, not -headless) in their
# own metadata regardless of what's already installed, and pip has no way
# to redirect that to opencv-python-headless for a transitive dependency —
# installing both variants side by side corrupts the shared cv2 install
# (whichever finishes writing its files last silently wins, verified: this
# broke cv2.imshow on a supposedly-headless install). --no-deps skips
# dependency resolution entirely for just these three, so opencv-python is
# never evaluated as a requirement at all. Safe because every *other*
# runtime dependency these three actually need (torch, numpy, pyzbar,
# quadrilateral-fitter, requests, tqdm, filelock, matplotlib, polars,
# psutil, PyYAML, Pillow, ultralytics-platform, ultralytics-thop,
# opencv-python-headless) is already pinned as its own line in
# requirements.txt and installed normally, above.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-deps ultralytics==8.4.123 qrdet==2.5 qreader==3.16

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
