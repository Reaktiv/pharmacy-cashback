"""Stage-by-stage diagnosis for a receipt image the bot refused.

Usage (from anywhere, no Django setup needed — apps.bot.qr is a pure module):
    python backend/apps/bot/diagnose_receipt.py chek1.jpg chek2.heic ...

Ask a customer whose receipt failed to forward you the original image, drop
it here, and this prints exactly which stage broke and what to change. It
runs the same ladder as apps/bot/qr.py but reports every step instead of the
first hit.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageOps  # noqa: E402

from apps.bot.qr import (  # noqa: E402
    _PREPROCESSORS,
    HEIF_SUPPORTED,
    MIN_USABLE_QR_PX,
    _qr_size,
    _read,
    decode_receipt_qr,
    normalize_check_url,
)

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def mark(ok: bool) -> str:
    return f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"


def diagnose(path: Path) -> None:
    print(f"\n{'=' * 72}\n{path.name}\n{'=' * 72}")
    data = path.read_bytes()
    print(f"file size            : {len(data) / 1024:.0f} KB")

    # --- stage 1: can we open it at all?
    try:
        img: Image.Image = Image.open(path)
        # .format is lost once exif_transpose/convert produce a new Image
        # object below (a known Pillow quirk) — capture it here, first.
        img_format = img.format
        img = ImageOps.exif_transpose(img)
        w, h = img.size
        mp = w * h / 1e6
        print(f"decoded by Pillow    : {mark(True)}  {img_format} {w}x{h} ({mp:.1f} MP)")
        if img_format in {"HEIF", "HEIC"} and not HEIF_SUPPORTED:
            print(f"  {RED}pillow-heif is not installed — production will reject this file{RESET}")
        if mp > 80:
            print(f"  {YELLOW}>80 MP: MAX_DECODE_PIXELS would reject this{RESET}")
        gray = np.asarray(img.convert("L"), dtype=np.uint8)
    except Exception as exc:
        print(f"decoded by Pillow    : {mark(False)}  {type(exc).__name__}: {exc}")
        if not HEIF_SUPPORTED:
            print(f"  {YELLOW}hint: pip install pillow-heif (iPhone uploads are HEIC){RESET}")
        return

    # --- stage 2: which preprocessing recovers the code?
    print(f"\n{DIM}decode strategies{RESET}")
    found = None
    for name, prep in _PREPROCESSORS:
        try:
            hits = _read(prep(gray))
        except Exception as exc:
            print(f"  {name:<12} {RED}error{RESET} {type(exc).__name__}: {exc}")
            continue
        if hits:
            size = _qr_size(hits[0]) // (2 if name == "upscale2x" else 1)
            print(f"  {name:<12} {mark(True)}  {len(hits)} code(s), ~{size}px")
            found = found or (name, hits[0], size)
        else:
            print(f"  {name:<12} {DIM}nothing{RESET}")

    # OpenCV's own detector is shown for comparison only — it was dropped
    # from apps/bot/qr.py's production ladder (see that module's docstring):
    # against realistic phone photos it never recovered a code zxing missed.
    try:
        txt, _, _ = cv2.QRCodeDetector().detectAndDecode(gray)
        print(f"  {'opencv':<12} {DIM}{'found' if txt else 'nothing'} (reference only){RESET}")
    except cv2.error:
        print(f"  {'opencv':<12} {DIM}error (reference only){RESET}")

    if not found:
        print(f"\n{RED}No QR found.{RESET}")
        print(f"  image is {gray.shape[1]}x{gray.shape[0]}")
        print("  Most common cause: the QR is too small in the frame. A receipt QR is")
        print(f"  ~45 modules wide and needs >= {MIN_USABLE_QR_PX}px to decode, so it must fill")
        print("  roughly 10% of the image width. If the customer photographed the whole")
        print("  receipt and Telegram then downscaled it to 1280px, the QR arrives at")
        print("  ~50-60px and is unrecoverable — see apps/bot/qr.py's module docstring.")
        return

    name, barcode, size = found
    value = barcode.text.strip()
    print(f"\nQR payload           : {value}")
    print(f"recovered by         : {name}, ~{size}px on a side")
    if size and size < MIN_USABLE_QR_PX * 1.3:
        print(f"  {YELLOW}marginal size — this one decoded, but similar photos will not{RESET}")

    # --- stage 3: does it survive check-URL validation?
    normalized = normalize_check_url(value)
    print(f"passes URL validation: {mark(normalized is not None)}")
    if normalized is None:
        print(
            f"  {RED}decoded fine but rejected before Celery — customer sees "
            f"receipt_untrusted_url{RESET}"
        )
        print("  Check host/path/params against apps/bot/qr.py's normalize_check_url.")
    elif normalized != value:
        print(f"  normalized to      : {normalized}")

    # --- stage 4: what the production function would return end to end
    result = decode_receipt_qr(data)
    print(f"\ndecode_receipt_qr()  : {result}")


def main() -> int:
    paths = [Path(a) for a in sys.argv[1:]]
    if not paths:
        print(__doc__)
        return 1
    print(f"pillow-heif installed: {HEIF_SUPPORTED}")
    for p in paths:
        if not p.exists():
            print(f"{RED}missing:{RESET} {p}")
            continue
        diagnose(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
