"""QR decoding for the receipt-photo cashback flow (see
apps/bot/tasks.py::process_receipt_photo). Pure sync, no aiogram — a
customer's photo bytes come in, a check URL (or nothing) comes out.

Detector: qreader (github.com/Eric-Canas/qreader). It is a two-stage
pipeline — a YOLOv8 model (via the qrdet package, PyTorch) first *finds* the
QR in the frame (bounding polygon, confidence), crops and deskews that
region, and only then hands the crop to pyzbar for the actual pixel decode.
That second stage is a real constraint worth being explicit about: the
decoder underneath is pyzbar, the same library this module previously
dropped (see git history: "Harden receipt QR decoding: zxing-cpp + OpenCV
fallback") after it failed on real, blurry customer photos and was replaced
with zxing-cpp. Swapping back to a pyzbar-based decoder is a deliberate,
informed choice, on the bet that YOLO's crop/deskeving recovers cases a
blind preprocessing ladder over the *whole frame* missed — rotation,
perspective skew, and a QR that isn't the dominant thing in the photo — even
though it does nothing for a QR that's simply too small or too motion-blurred
to resolve at the pixel level; see MIN_USABLE_QR_PX below, which is a
property of the photo, not of whichever decoder reads it.

There is no local preprocessing ladder here anymore (plain/upscale/unsharp/
adaptive-threshold, previously tuned around zxing's behavior) — qreader runs
its own multi-scale, multi-correction retry internally (see its
_decode_qr_zbar), and stacking a second, differently-tuned ladder in front
of a detector that does its own would mostly just cost CPU. Losing
per-strategy attribution is the trade for that simplicity: QrResult.strategy
is now always "qreader" (previously "plain"/"upscale2x"/"unsharp"/
"adaptive") — see apps/bot/diagnose_receipt.py for per-detection diagnostics
(confidence, bbox size, decode outcome) instead.

decode_receipt_qr reports *why* it failed (QrFailure.reason) and, on
success, how large the QR was in the source frame (QrResult.size_px) — the
size is worth logging: it turns "bot QR o'qimayapti" reports into a number
instead of a guess about how far away the customer stood.
"""

from __future__ import annotations

import io
import logging
import threading
from dataclasses import dataclass
from typing import NamedTuple, TypedDict, cast
from urllib.parse import parse_qs, urlencode, urlparse

import numpy as np
from PIL import Image, ImageOps
from qreader import QReader


# qreader ships no py.typed marker and detect_and_decode's own signature
# declares a bare typing.Union of its return_detections=True and =False
# shapes with no overload keyed to that literal, so mypy can't narrow it —
# every call site that passes return_detections=True casts to this alias
# instead. QReader.detect's docstring lists many more keys (bbox_xyxy,
# cxcy, polygon_xy, quad_xy, padded_quad_xy, plus each key's "n"
# (normalized) variant) than this TypedDict declares — only "confidence"
# and "wh" are actually read here, and a TypedDict only constrains what you
# may access through it, not what keys the real dict is allowed to have.
class _QreaderDetection(TypedDict):
    confidence: float
    wh: tuple[float, float]


_QreaderDetectAndDecodeResult = tuple[
    tuple[str | None, ...], tuple[_QreaderDetection, ...]
]

logger = logging.getLogger(__name__)

# iPhones send HEIC when a receipt photo is attached as a file ("Actual
# Size") instead of sent as a Telegram "photo". Without this, every such
# upload dies in Image.open with an UnidentifiedImageError and the customer
# gets no response at all — exactly the upload path apps/bot/i18n.py's
# receipt_ask_photo string tells customers to use when the compressed
# "photo" path fails.
try:
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF_SUPPORTED = True
except ImportError:  # pragma: no cover - depends on deployment image
    HEIF_SUPPORTED = False
    logger.warning("pillow-heif not installed: HEIC/HEIF receipt uploads will be rejected")

# Belt and braces against Pillow's EPS plugin, which shells out to
# Ghostscript on load (a well-known RCE surface — see _load_grayscale's
# docstring for why the format check below is what actually matters here).
# EPS is deliberately not in _ALLOWED_IMAGE_FORMATS, so the format check
# already refuses it before any pixel decode; this goes further and removes
# Pillow's ability to identify EPS at all, so nothing else added to this
# module later could reintroduce the risk by skipping that check.
#
# Image.init() is forced FIRST and deliberately, not left to run lazily.
# Pillow only registers a handful of "common" plugins (BMP/GIF/JPEG/PNG) by
# default (Image.preinit()) and defers the rest, including EpsImagePlugin,
# until Image.open() itself needs them — which happens by loading EVERY
# bundled plugin, unconditionally, the first time an image fails to
# identify against the common set. Removing "EPS" from Image.ID/OPEN before
# that first full load has happened is removing something that isn't
# registered yet: it's a silent no-op, and the very first EPS payload
# Image.open() ever sees back in _load_grayscale would trigger that full
# load itself and re-register EPS again, undoing this block entirely
# (verified: skipping the explicit init() call below reproduces exactly
# that failure). Calling Image.init() here forces the one-time full plugin
# load to happen NOW, before EPS is removed, and Pillow's own internal
# "already initialized" guard means it never runs again for the rest of the
# process — so the removal, once it actually has something to remove, stays
# removed permanently.
Image.init()
if "EPS" in Image.ID:
    Image.ID.remove("EPS")
Image.OPEN.pop("EPS", None)
for _eps_ext in (".eps", ".ps"):
    Image.EXTENSION.pop(_eps_ext, None)

# Formats decode_receipt_qr actually makes sense of. Checked in
# _load_grayscale immediately after Image.open() — before ANY pixel data is
# touched — rather than as a client-supplied MIME allowlist (which used to
# live in apps/bot/handlers.py and is why that pre-filter is now loose: see
# its own comment). MPO is not optional — iPhone HDR and portrait shots are
# multi-picture JPEG files and Pillow reports format="MPO" for them;
# omitting it would silently break a large share of iPhone uploads, the
# same class of bug this whole change fixes.
_ALLOWED_IMAGE_FORMATS = {"JPEG", "MPO", "PNG", "WEBP", "HEIF", "HEIC", "GIF", "BMP", "TIFF"}


class _UnsupportedImageFormat(Exception):
    """Raised by _load_grayscale for a format outside _ALLOWED_IMAGE_FORMATS
    — deliberately not a ValueError (decode_receipt_qr's except ValueError
    clause is reserved for the MAX_DECODE_PIXELS ceiling specifically), so
    it falls through to decode_receipt_qr's generic except Exception clause
    and reports QrFailure(reason="unreadable_image")."""


# A 50MP phone sensor produces ~50e6 pixels, and 100MP+ sensors are common
# now — rejecting at 36MP throws away exactly the high-resolution uploads
# most likely to actually contain a decodable QR (see module docstring:
# resolution is what the document upload path exists to preserve). This is
# a hard refusal (decompression-bomb guard), checked from the file header
# BEFORE any pixel data is decoded — see _load_grayscale. Images under this
# ceiling are then downscaled to MAX_WORKING_SIDE before decoding, so actual
# memory/CPU use stays bounded regardless of the original resolution.
MAX_DECODE_PIXELS = 80_000_000
MAX_WORKING_SIDE = 4000

# A receipt QR is ~45 modules across including its quiet zone; a module
# needs roughly 2 image pixels to survive binarization, so ~90px on a side
# is the rough floor a *plain* decoder needs. qreader's YOLO crop-and-
# upscale step measurably pushes this lower in practice — a clean synthetic
# 37px QR decoded fine in testing — so this is deliberately not used to gate
# decode_receipt_qr itself; it's a conservative diagnostic heuristic only,
# reported via QrResult.size_px and used by diagnose_receipt.py to flag a
# photo as "marginal" even when it happened to decode.
MIN_USABLE_QR_PX = 90

# Constructing QReader() loads a PyTorch/YOLO model into memory — a
# multi-second, ~hundreds-of-MB-RSS cost — so it happens lazily, on first
# use, not at import time: a uvicorn worker (config/asgi.py runs
# --workers 3) that never handles a receipt photo never pays it, and one
# that does pays it exactly once. model_size="s" (small) is qreader's own
# default and recommendation — "n" is faster but measurably less accurate,
# "m"/"l" cost more CPU time per photo for accuracy this model doesn't need
# (a receipt QR is a clean, high-contrast printed code, not a QR "in the
# wild" at an odd angle on a curved surface, which is qrdet's harder target
# case). See the Dockerfile for how the weights are baked into the image at
# build time so this lazy load never needs network access at runtime.
_qreader_lock = threading.Lock()
_qreader_instance: QReader | None = None


def _get_qreader() -> QReader:
    """Returns the shared, process-wide QReader instance, constructing it on
    first call. apps/bot/handlers.py invokes decode_receipt_qr via
    sync_to_async(..., thread_sensitive=True), so two customers' photos
    landing on a cold worker at nearly the same moment both reach this
    function — the lock (checked-locked-checked) ensures only one of them
    actually constructs (and loads) the model."""
    global _qreader_instance
    if _qreader_instance is None:
        with _qreader_lock:
            if _qreader_instance is None:
                _qreader_instance = QReader(model_size="s")
    return _qreader_instance


@dataclass(frozen=True)
class QrResult:
    value: str
    strategy: str
    size_px: int  # longest side of the detected QR in the source frame


@dataclass(frozen=True)
class QrFailure:
    reason: str  # "unreadable_image" | "image_too_large" | "not_found"
    detail: str = ""  # diagnostic only — never shown to the customer


# --------------------------------------------------------------------- loading


class _LoadedImage(NamedTuple):
    gray: np.ndarray
    source_size: tuple[int, int]  # (width, height) as originally uploaded, pre-downscale


def _load_grayscale(image_bytes: bytes) -> _LoadedImage:
    """Decode bytes to a grayscale array, honouring EXIF rotation.

    Opening a file and reading its declared width/height is a header-only
    read; Pillow doesn't decode pixel data until something forces it to
    (exif_transpose/convert below do). The size check below runs on that
    lazy, undecoded image specifically so an oversized image is refused
    BEFORE the costly decode, not after — checking post-decode would defeat
    the point of a memory ceiling.

    Between that check and the actual decode, img.draft() tells the JPEG
    decoder to decode straight to a downscaled grayscale image instead of
    full resolution — we're about to grayscale-and-downscale everything
    anyway (see MAX_WORKING_SIDE below), so a 48MP phone photo (well under
    MAX_DECODE_PIXELS, and a normal camera default now) would otherwise pay
    the full cost of decoding 48 million pixels into memory only to throw
    almost all of them away microseconds later in the resize call at the
    bottom. draft() is JPEG-only; it's a documented no-op for every other
    format (PNG, WEBP, HEIC), so it's safe to call unconditionally.

    The target passed to draft() MUST be the aspect-ratio-preserving
    downscaled size, not (MAX_WORKING_SIDE, MAX_WORKING_SIDE). draft()'s
    contract is "give me something no smaller than this target in BOTH
    dimensions" — it only picks from 1x/1/2/1/4/1/8 reductions, and rejects
    any reduction that would put either dimension below the target. For a
    6000x8000 image, requesting (4000, 4000) makes Pillow refuse to scale at
    all: 1/2 scale is (3000, 4000), and 3000 < 4000 fails the "not smaller
    than" test on width alone, so it falls back to full resolution — exactly
    the cost this is meant to avoid. Requesting the correctly-scaled (3000,
    4000) instead lets 1/2 scale satisfy the constraint in both dimensions.
    Do not "simplify" this back to a bare (MAX_WORKING_SIDE, MAX_WORKING_SIDE)
    tuple.

    SECURITY-CRITICAL ORDERING: the img.format check right after Image.open()
    below must stay exactly there — between Image.open() and the first thing
    that forces a pixel decode (img.draft() doesn't; exif_transpose() and
    convert() do). Image.open() is lazy: it identifies a file's format from
    its header without decoding any pixel data, so Image.open() on EPS bytes
    succeeds and reports format="EPS" without ever invoking Ghostscript —
    Pillow's EPS plugin only shells out to Ghostscript (a well-known RCE
    surface) once something forces that decode. A format check placed after
    exif_transpose or convert would already have run Ghostscript by the time
    it rejects the file; checking here, on the still-undecoded img, refuses
    it safely. (EPS is also fully deregistered at import time above, as a
    second, independent layer — but that's a backstop, not a substitute for
    getting this ordering right.)"""
    img: Image.Image = Image.open(io.BytesIO(image_bytes))
    if img.format not in _ALLOWED_IMAGE_FORMATS:
        raise _UnsupportedImageFormat(f"unsupported format: {img.format}")

    w, h = img.size
    source_size = (w, h)
    if w * h > MAX_DECODE_PIXELS:
        raise ValueError(f"image too large: {w}x{h}")

    draft_ratio = min(1.0, MAX_WORKING_SIDE / max(w, h))
    img.draft("L", (round(w * draft_ratio), round(h * draft_ratio)))

    # Phones record orientation in EXIF instead of rotating pixels. Pillow
    # does not apply it automatically, and a customer's receipt is just as
    # often photographed in portrait as landscape — this must run
    # regardless of decoder. Must run after draft() (draft is only
    # effective before the first pixel load, and exif_transpose forces that
    # load) and before the array conversion (so the rotation is baked into
    # the pixels the decoder sees).
    img = ImageOps.exif_transpose(img)
    img = img.convert("L")

    # draft() only lands on 1x/1/2/1/4/1/8 and is a no-op for non-JPEG input,
    # so the image actually in hand here can still be larger than
    # MAX_WORKING_SIDE — this exact resize is what guarantees the ceiling,
    # draft() is purely a cost-saving head start on JPEG.
    w, h = img.size
    if max(w, h) > MAX_WORKING_SIDE:
        scale = MAX_WORKING_SIDE / max(w, h)
        img = img.resize((round(w * scale), round(h * scale)), Image.Resampling.LANCZOS)
    return _LoadedImage(gray=np.asarray(img, dtype=np.uint8), source_size=source_size)


# ------------------------------------------------------------------- decoding


def decode_receipt_qr(image_bytes: bytes) -> QrResult | QrFailure:
    """Find a QR code in a photographed receipt.

    The failure reason is deliberately specific: an image we could not even
    open (corrupt bytes, unsupported format) is a different problem for a
    customer than an image with no QR in it, which is different again from
    an image refused for being over the size ceiling — see QrFailure.reason.
    """
    try:
        gray, source_size = _load_grayscale(image_bytes)
    except ValueError as exc:
        # The ValueError's own message already carries the offending WxH
        # (see the "image too large: {w}x{h}" raise in _load_grayscale) —
        # nothing else to attach, since the ceiling is checked from the
        # header alone and nothing past that point ever decodes.
        logger.warning("receipt_qr_decode_failed reason=image_too_large detail=%s", exc)
        return QrFailure("image_too_large", str(exc))
    except Exception as exc:
        # Genuinely unknown dimensions here in general — Image.open() itself
        # may be what failed (corrupt bytes, unsupported format), so there's
        # no size to log.
        hint = "" if HEIF_SUPPORTED else " (pillow-heif missing; HEIC unsupported)"
        detail = f"{type(exc).__name__}: {exc}{hint}"
        logger.warning("receipt_qr_decode_failed reason=unreadable_image detail=%s", detail)
        return QrFailure("unreadable_image", detail)

    # qreader accepts a grayscale (H, W) array directly — its own
    # detect()/_prepare_input repeats it to 3 channels for the YOLO model
    # internally; the pyzbar decode step underneath also works directly on
    # 2D input. Nothing here needs its own RGB conversion.
    try:
        decoded_values, detections = cast(
            _QreaderDetectAndDecodeResult,
            _get_qreader().detect_and_decode(image=gray, return_detections=True),
        )
    except Exception as exc:  # a detector/decoder crash must not kill the request
        detail = f"qreader raised {type(exc).__name__}: {exc}"
        logger.warning(
            "receipt_qr_decode_failed reason=not_found detail=%s source=%dx%d",
            detail,
            source_size[0],
            source_size[1],
        )
        return QrFailure("not_found", detail)

    # detect_and_decode returns one (possibly-None) decoded string per
    # detection, in the same order — a receipt photo can contain more than
    # one QR-shaped pattern (a barcode misclassified, packaging in the
    # background), so among the ones that actually decoded, prefer the
    # detector's highest-confidence match rather than just the first.
    hits = [
        (detection, value)
        for detection, value in zip(detections, decoded_values, strict=True)
        if value
    ]
    if not hits:
        detail = (
            f"{len(detections)} detection(s), 0 decoded, frame {gray.shape[1]}x{gray.shape[0]}"
        )
        logger.warning(
            "receipt_qr_decode_failed reason=not_found detail=%s source=%dx%d",
            detail,
            source_size[0],
            source_size[1],
        )
        return QrFailure("not_found", detail)

    detection, value = max(hits, key=lambda pair: pair[0]["confidence"])
    w, h = detection["wh"]
    size = int(max(w, h))
    logger.info(
        "receipt_qr_decode_success strategy=qreader size_px=%d source=%dx%d frame=%dx%d",
        size,
        source_size[0],
        source_size[1],
        gray.shape[1],
        gray.shape[0],
    )
    return QrResult(value=value.strip(), strategy="qreader", size_px=size)


# ------------------------------------------------------------ URL validation

# Real fiscal QR codes encode a link of the form
#   https://ofd.soliq.uz/epi?t=<terminal>&r=<receipt>&c=<YYYYMMDDHHMMSS>&s=<sign>
# (confirmed against multiple independent OFD-integration docs). /check with
# the same four parameters also appears in the wild from other integrations.
# Accepting only one of the two paths silently rejects genuine receipts, and
# the customer experiences that identically to "the bot cannot read my QR
# code" — is_trusted_check_url's old prefix check on /check alone did
# exactly this.
_ALLOWED_HOSTS = {"ofd.soliq.uz"}
_ALLOWED_PATHS = {"/epi", "/check"}
_REQUIRED_PARAMS = ("t", "r", "c", "s")
_PARAM_MAX_LEN = 64


def normalize_check_url(raw: str) -> str | None:
    """Validate a decoded QR payload and return a URL rebuilt from it, or
    None if the payload isn't a genuine soliq.uz receipt link.

    A QR code is attacker-controlled input (anyone can print one), and this
    module's result is what apps.bot.tasks points a real headless browser
    at. Rebuilding the URL from individually-validated components — rather
    than checking that the raw string merely starts with the right host/
    path — means Playwright always navigates to a string this function
    constructed, never to one that only looked right (userinfo tricks like
    https://ofd.soliq.uz@evil.example/epi, embedded credentials, non-default
    ports, fragments, duplicated query keys).

    An explicit http:// scheme is deliberately NOT upgraded to https:// here
    — only a bare, schemeless payload ("ofd.soliq.uz/epi?...", which some
    printers are known to emit) gets a scheme prepended. This isn't about
    closing a hole in the check below: host/path/params are validated on the
    *parsed* result regardless of scheme, and the URL returned always has
    https:// on it either way, so an upgraded http:// link would have been
    validated exactly as strictly as one that arrived as https:// already.
    The reason to reject it instead is narrower: a genuine fiscal QR never
    declares http://, so one that does is an anomalous payload, and there's
    no upside to widening what this accepts to cover input real receipts
    don't produce. This also just preserves the original implementation's
    behavior, which rejected http:// the same way."""
    if not raw:
        return None
    candidate = raw.strip()
    if candidate.lower().startswith("ofd.soliq.uz"):
        candidate = "https://" + candidate

    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None

    if parsed.scheme != "https":
        return None
    if parsed.username or parsed.password:
        return None
    if parsed.port not in (None, 443):
        return None
    if (parsed.hostname or "").lower() not in _ALLOWED_HOSTS:
        return None

    path = parsed.path.rstrip("/") or "/"
    if path not in _ALLOWED_PATHS:
        return None

    params = parse_qs(parsed.query, keep_blank_values=False)
    clean: dict[str, str] = {}
    for key in _REQUIRED_PARAMS:
        values = params.get(key)
        if not values or len(values) != 1:
            return None
        value = values[0].strip()
        if not value or len(value) > _PARAM_MAX_LEN:
            return None
        if not value.replace("-", "").isalnum():
            return None
        clean[key] = value

    host = (parsed.hostname or "").lower()
    return f"https://{host}{path}?{urlencode(clean)}"


def is_trusted_check_url(raw: str) -> bool:
    """Backwards-compatible boolean wrapper around normalize_check_url —
    apps.bot.tasks._process_receipt_photo_sync still calls this for its
    defense-in-depth re-check."""
    return normalize_check_url(raw) is not None
