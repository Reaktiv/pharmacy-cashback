"""QR decoding for the receipt-photo cashback flow (see
apps/bot/tasks.py::process_receipt_photo). Pure sync, no aiogram — a
customer's photo bytes come in, a check URL (or nothing) comes out.

Staged, bounded decoder pipeline (see decode_receipt_qr): a handful of
cheap zxing-cpp variants first, then OpenCV's own detector as a last
resort, stopping at the first hit. This is deliberately NOT an exhaustive
"every preprocessing variant x every decoder" matrix — this runs
synchronously in the Telegram handler (apps.bot.handlers.on_receipt_photo)
before any Celery task exists, so it must stay fast even under concurrent
load. It's also not exhaustive because it doesn't need to be: real-photo
testing against a genuinely degraded receipt image showed that once
zxing-cpp's own bit sampling reports a checksum error, no amount of
additional preprocessing or a second decoder recovers it — the modules
themselves are unreadable, not just poorly thresholded. Preprocessing
variants exist here for the *recoverable* middle ground (mild blur, low
contrast, moderate scale), not as a hope of rescuing every photo.

pyzbar (this module's original decoder, before zxing-cpp replaced it) is
deliberately not part of this pipeline — see decode_receipt_qr's docstring
below for why.
"""

import logging
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import urlparse

import cv2
import numpy as np
import zxingcpp
from PIL import Image

logger = logging.getLogger(__name__)

# The only host apps/bot ever lets Playwright navigate to for a scanned
# receipt (apps/bot/tasks.py's _fetch_receipt_via_playwright) — ofd.soliq.uz
# is Uzbekistan's official fiscal-receipt verification portal, the source
# of truth for what a QR code on a real receipt encodes.
TRUSTED_CHECK_HOST = "ofd.soliq.uz"

_ZXING_QR_ONLY = zxingcpp.BarcodeFormats(zxingcpp.BarcodeFormat.QRCode)

# Explicit, intentional ceiling (audit finding M-5) rather than relying
# incidentally on Pillow's default MAX_IMAGE_PIXELS decompression-bomb
# guard (~89 megapixels) and Telegram's 20MB file-size cap. A real receipt
# photo from any phone camera is nowhere near this large; this exists so
# the bound on memory used by the 2x-upscale stage below is something this
# codebase actually chose and tests, not a side effect of two other
# libraries' unrelated defaults.
MAX_RECEIPT_IMAGE_PIXELS = 6000 * 6000


@dataclass
class QRDecodeResult:
    """value is the raw decoded text (still untrusted — is_trusted_check_url
    below is the actual security gate). decoder records which stage
    produced it ("zxing" or "opencv"), for logging/diagnostics only; callers
    must never branch business logic on it."""

    value: str
    decoder: str


def _blur_variance(gray: np.ndarray) -> float:
    """Laplacian variance — a rough, well-known blur heuristic (low value =
    likely blurry). Logged alongside decode outcomes so it's possible to
    later see whether failures correlate with blur, but this deliberately
    has no hardcoded reject threshold: a heuristic is not a substitute for
    knowing that a given blur level actually makes a QR undecodable."""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _zxing_decode(image) -> str | None:
    codes = zxingcpp.read_barcodes(image, formats=_ZXING_QR_ONLY)
    return codes[0].text if codes else None


def decode_receipt_qr(image_bytes: bytes) -> QRDecodeResult | None:
    """The first QR code's decoded text found in the image, or None if the
    bytes aren't a readable image or no decoder can find a QR code in it.

    Stage 1 — zxing-cpp against a few cheap, deterministic variants (original,
    grayscale, 2x upscale, adaptive threshold), cheapest/most-likely first,
    stopping at the first hit.

    Stage 2 — cv2.QRCodeDetector as a final fallback. This is a genuinely
    different algorithm (its own localization and bit-sampling), so it's a
    real second opinion rather than another pass through the same decoder.

    pyzbar (zbar) is NOT a third stage here even though it was this
    project's original decoder. It was replaced with zxing-cpp specifically
    because zbar decodes strictly fewer real receipt photos than zxing-cpp
    does; keeping it as a "just in case" fallback would only add a system
    dependency (libzbar0) for a stage that, in practice, never succeeds
    where zxing-cpp has already failed."""
    try:
        pil_image = Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return None

    if pil_image.width * pil_image.height > MAX_RECEIPT_IMAGE_PIXELS:
        logger.info(
            "receipt_qr_decode_rejected reason=too_large width=%d height=%d",
            pil_image.width,
            pil_image.height,
        )
        return None

    bgr = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    logger.info(
        "receipt_qr_decode_started width=%d height=%d bytes=%d blur_variance=%.1f",
        pil_image.width,
        pil_image.height,
        len(image_bytes),
        _blur_variance(gray),
    )

    zxing_variants = [
        ("original", pil_image),
        ("grayscale", Image.fromarray(gray)),
        (
            "upscaled",
            Image.fromarray(
                cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            ),
        ),
        (
            "adaptive_threshold",
            Image.fromarray(
                cv2.adaptiveThreshold(
                    gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 5
                )
            ),
        ),
    ]
    for variant_name, variant_image in zxing_variants:
        text = _zxing_decode(variant_image)
        if text:
            logger.info("receipt_qr_decode_success decoder=zxing variant=%s", variant_name)
            return QRDecodeResult(value=text, decoder="zxing")

    text, _points, _straight = cv2.QRCodeDetector().detectAndDecode(bgr)
    if text:
        logger.info("receipt_qr_decode_success decoder=opencv")
        return QRDecodeResult(value=text, decoder="opencv")

    logger.info("receipt_qr_decode_failed")
    return None


def is_trusted_check_url(url: str) -> bool:
    """SSRF guard: a QR code is attacker-controlled input (anyone can print
    one), so before ever pointing the bot's own headless browser at
    whatever URL it decodes to, this must be exactly ofd.soliq.uz's own
    check page — never an arbitrary internal or external host."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname == TRUSTED_CHECK_HOST
        and parsed.path.startswith("/check")
    )
