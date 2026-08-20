"""Stage-by-stage diagnosis for a receipt image the bot refused.

Usage (from anywhere, no Django setup needed — apps.bot.qr is a pure module):
    python backend/apps/bot/diagnose_receipt.py chek1.jpg chek2.heic ...

Ask a customer whose receipt failed to forward you the original image, drop
it here, and this prints every detection qreader found (confidence, bbox
size, whether pyzbar could decode that crop) instead of just the first hit
decode_receipt_qr itself stops at.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import numpy as np  # noqa: E402
from PIL import Image, ImageOps  # noqa: E402

from apps.bot.qr import (  # noqa: E402
    HEIF_SUPPORTED,
    MIN_USABLE_QR_PX,
    _get_qreader,
    _QreaderDetectAndDecodeResult,
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

    # --- stage 2: what does qreader's YOLO detector find, and does pyzbar
    # decode what it crops out?
    print(f"\n{DIM}qreader detections{RESET}")
    decoded_values, detections = cast(
        _QreaderDetectAndDecodeResult,
        _get_qreader().detect_and_decode(image=gray, return_detections=True),
    )
    best: tuple[float, str] | None = None
    if not detections:
        print(f"  {DIM}no QR-shaped region found in the frame{RESET}")
    for i, (detection, value) in enumerate(zip(detections, decoded_values, strict=True)):
        confidence = detection["confidence"]
        w_box, h_box = detection["wh"]
        size = int(max(w_box, h_box))
        if value:
            print(f"  #{i} conf={confidence:.2f} ~{size}px {mark(True)}  decoded")
            if best is None or confidence > best[0]:
                best = (confidence, value)
        else:
            print(f"  #{i} conf={confidence:.2f} ~{size}px {mark(False)}  pyzbar failed")

    if best is None:
        print(f"\n{RED}No QR decoded.{RESET}")
        print(f"  image is {gray.shape[1]}x{gray.shape[0]}")
        print("  Most common cause: the QR is too small in the frame. A receipt QR is")
        print(f"  ~45 modules wide and needs >= {MIN_USABLE_QR_PX}px to decode, so it must fill")
        print("  roughly 10% of the image width. If the customer photographed the whole")
        print("  receipt and Telegram then downscaled it to 1280px, the QR arrives at")
        print("  ~50-60px and is unrecoverable — see apps/bot/qr.py's module docstring.")
        print("  If qreader found zero detections at all (not even a failed-to-decode")
        print("  one), the YOLO model itself didn't recognize a QR-like region — that's")
        print("  a different failure mode than pyzbar failing on a found-but-unreadable")
        print("  crop, and no amount of pyzbar-side preprocessing would have helped.")
        return

    confidence, value = best
    print(f"\nQR payload           : {value}")
    print(f"recovered at         : confidence={confidence:.2f}")

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
