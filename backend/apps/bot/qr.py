"""QR decoding for the receipt-photo cashback flow (see
apps/bot/tasks.py::process_receipt_photo). Pure sync, no aiogram — a
customer's photo bytes come in, a check URL (or nothing) comes out.
"""

from io import BytesIO
from urllib.parse import urlparse

from PIL import Image
from pyzbar.pyzbar import decode as decode_qr_codes

# The only host apps/bot ever lets Playwright navigate to for a scanned
# receipt (apps/bot/tasks.py's _fetch_receipt_via_playwright) — ofd.soliq.uz
# is Uzbekistan's official fiscal-receipt verification portal, the source
# of truth for what a QR code on a real receipt encodes.
TRUSTED_CHECK_HOST = "ofd.soliq.uz"


def extract_url_from_photo(image_bytes: bytes) -> str | None:
    """The first QR code's decoded text found in the image, or None if the
    bytes aren't a readable image or no QR code is found."""
    try:
        image = Image.open(BytesIO(image_bytes))
    except Exception:
        return None
    codes = decode_qr_codes(image)
    if not codes:
        return None
    return codes[0].data.decode("utf-8", errors="ignore")


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
