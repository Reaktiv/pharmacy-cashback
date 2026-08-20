"""Summarizes the receipt-QR decode path (apps/bot/handlers.py,
apps/bot/qr.py) from apps.bot's structured logs.

Reads plain-text log lines (a file via --file, or stdin — e.g. `docker
compose logs web worker | python manage.py receipt_qr_report`) and answers
three questions about the events apps.bot.handlers._handle_receipt_image
emits: receipt_qr_accepted, receipt_qr_rejected, receipt_qr_untrusted. The
exact line format comes from config.settings.LOGGING's "apps_console"
formatter, attached to the "apps" logger (every apps.* module, project-wide)
— see that file's own comment for why: without it, INFO-level records like
receipt_qr_accepted were silently dropped before reaching any handler, not
just going unformatted.

One line looks like:
    2026-08-18T13:05:07.536Z INFO apps.bot.handlers receipt_qr_accepted \
        upload_kind=photo strategy=qreader size_px=145

_LINE_RE uses re.search rather than re.match specifically so a
`docker compose logs` service-name prefix ("web-1  | ...") ahead of the
timestamp doesn't prevent a match — it just finds the timestamp wherever it
starts.

The two free-text fields (receipt_qr_rejected's detail=, receipt_qr_
untrusted's raw_value=) are logged with %r (repr()), not %s — see those log
call sites' own comments for why (a QR code is attacker-controlled input and
could otherwise contain an embedded newline, splitting or spoofing a log
line). _parse_line reverses that with ast.literal_eval.
"""

from __future__ import annotations

import ast
import re
import statistics
import sys
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from django.core.management.base import BaseCommand

_LINE_RE = re.compile(
    r"(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{1,6}Z)\s+"
    r"(?P<level>\w+)\s+"
    r"(?P<logger>\S+)\s+"
    r"(?P<message>.*)$"
)

# One pattern per event apps.bot.handlers._handle_receipt_image emits, in the
# exact field order those logger.warning()/logger.info() calls use. detail/
# raw_value are always the LAST field on their line specifically so ".*" can
# safely capture "everything to end of line" without needing to know where a
# repr()'d value's own content ends.
_EVENT_PATTERNS: dict[str, re.Pattern[str]] = {
    "receipt_qr_accepted": re.compile(
        r"^receipt_qr_accepted upload_kind=(?P<upload_kind>\S+) "
        r"strategy=(?P<strategy>\S+) size_px=(?P<size_px>\d+)$"
    ),
    "receipt_qr_rejected": re.compile(
        r"^receipt_qr_rejected upload_kind=(?P<upload_kind>\S+) "
        r"reason=(?P<reason>\S+) detail=(?P<detail>.*)$"
    ),
    "receipt_qr_untrusted": re.compile(
        r"^receipt_qr_untrusted upload_kind=(?P<upload_kind>\S+) raw_value=(?P<raw_value>.*)$"
    ),
}

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

_SIZE_BUCKET_EDGES = [90, 110, 130, 160, 200]
_SIZE_BUCKET_LABELS = ["<90", "90-109", "110-129", "130-159", "160-199", "200+"]


@dataclass(frozen=True)
class ReceiptQrEvent:
    timestamp: datetime  # naive, UTC (matches the "...Z" logged timestamp)
    name: str  # "receipt_qr_accepted" | "receipt_qr_rejected" | "receipt_qr_untrusted"
    fields: dict[str, str]


def _decode_repr_field(raw: str) -> str:
    """Reverses the %r the two free-text log fields are written with. Falls
    back to the raw captured text for a line that predates this format
    (logged with %s) or is otherwise not a valid Python string literal,
    rather than dropping the event."""
    try:
        value = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return raw
    return value if isinstance(value, str) else raw


def parse_line(line: str) -> ReceiptQrEvent | None:
    """None for a line that isn't one of the three receipt-QR events (the
    overwhelming majority of any real log — this is a filter, not just a
    parser) or that doesn't parse cleanly."""
    line_match = _LINE_RE.search(line)
    if line_match is None:
        return None

    try:
        timestamp = datetime.strptime(line_match.group("timestamp"), _TIMESTAMP_FORMAT)
    except ValueError:
        return None

    message = line_match.group("message")
    for name, pattern in _EVENT_PATTERNS.items():
        event_match = pattern.match(message)
        if event_match is None:
            continue
        fields = event_match.groupdict()
        for key in ("detail", "raw_value"):
            if key in fields:
                fields[key] = _decode_repr_field(fields[key])
        return ReceiptQrEvent(timestamp=timestamp, name=name, fields=fields)

    return None


def parse_lines(lines) -> list[ReceiptQrEvent]:
    events = []
    for line in lines:
        event = parse_line(line)
        if event is not None:
            events.append(event)
    return events


def _percent(part: int, whole: int) -> str:
    return f"{part / whole:.1%}" if whole else "n/a"


def _quantiles(sizes: list[int]) -> tuple[float, float, float]:
    """(median, p25, p90). statistics.quantiles needs >= 2 points; with
    exactly one, every percentile is that one point by definition."""
    if len(sizes) == 1:
        return float(sizes[0]), float(sizes[0]), float(sizes[0])
    median = statistics.median(sizes)
    cut_points = statistics.quantiles(sizes, n=100, method="inclusive")
    return median, cut_points[24], cut_points[89]  # 25th, 90th percentile


def _size_histogram(sizes: list[int]) -> list[int]:
    buckets = [0] * len(_SIZE_BUCKET_LABELS)
    for size_px in sizes:
        buckets[bisect_right(_SIZE_BUCKET_EDGES, size_px)] += 1
    return buckets


def _url_path(raw_value: str) -> str:
    if not raw_value:
        return "(empty)"
    try:
        path = urlparse(raw_value).path
    except ValueError:
        return "(unparseable)"
    return path or "(no path)"


def build_report(events: list[ReceiptQrEvent], *, since: datetime, until: datetime) -> str:
    accepted = [e for e in events if e.name == "receipt_qr_accepted"]
    rejected = [e for e in events if e.name == "receipt_qr_rejected"]
    untrusted = [e for e in events if e.name == "receipt_qr_untrusted"]

    lines = [
        f"Receipt-QR report: {since:%Y-%m-%d %H:%M} to {until:%Y-%m-%d %H:%M} UTC "
        f"({(until - since).days} days)",
        f"Matched {len(events)} receipt_qr_* events "
        f"({len(accepted)} accepted, {len(rejected)} rejected, {len(untrusted)} untrusted).",
        "",
    ]

    # --- 1. untrusted check URLs ------------------------------------------
    # "successful decode" here means the QR itself was read fine -- accepted
    # and untrusted both start from that; they diverge only on whether
    # normalize_check_url trusted the result (see apps/bot/handlers.py).
    successful_decodes = len(accepted) + len(untrusted)
    lines.append("== 1. Untrusted check URLs ==")
    lines.append(
        f"receipt_qr_untrusted: {len(untrusted)} "
        f"({_percent(len(untrusted), successful_decodes)} of {successful_decodes} successful "
        f"decodes: {len(untrusted)} untrusted + {len(accepted)} accepted)"
    )
    if untrusted:
        path_counts = Counter(_url_path(e.fields["raw_value"]) for e in untrusted)
        lines.append("URL paths seen in the (truncated) raw payload:")
        for path, count in path_counts.most_common():
            lines.append(f"  {path:<20} {count}")
    lines.append("")

    # --- 2. QR size at successful decode -----------------------------------
    lines.append("== 2. QR size at successful decode (size_px) ==")
    if accepted:
        sizes = sorted(int(e.fields["size_px"]) for e in accepted)
        median, p25, p90 = _quantiles(sizes)
        lines.append(f"accepted: {len(sizes)}")
        lines.append(f"median: {median:.0f}px   p25: {p25:.0f}px   p90: {p90:.0f}px")
        if median <= 100:
            lines.append(
                "  -> median is close to the ~90px decode floor: most customers are only "
                "just scraping through. The \"photograph the QR close up\" instruction "
                "likely isn't landing yet."
            )
        histogram = _size_histogram(sizes)
        lines.append("histogram:")
        for label, count in zip(_SIZE_BUCKET_LABELS, histogram, strict=True):
            lines.append(f"  {label:<8}: {count:>4}  ({_percent(count, len(sizes))})")
    else:
        lines.append("No accepted decodes in this window.")
    lines.append("")

    # --- 3. upload_kind split ------------------------------------------------
    lines.append("== 3. Upload kind ==")
    accepted_by_kind = Counter(e.fields["upload_kind"] for e in accepted)
    rejected_by_kind = Counter(e.fields["upload_kind"] for e in rejected)
    kinds = sorted(set(accepted_by_kind) | set(rejected_by_kind))
    if kinds:
        lines.append(f"{'':<12}{'accepted':>10}{'rejected':>10}{'success rate':>15}")
        for kind in kinds:
            kind_accepted = accepted_by_kind[kind]
            kind_rejected = rejected_by_kind[kind]
            rate = _percent(kind_accepted, kind_accepted + kind_rejected)
            lines.append(f"{kind:<12}{kind_accepted:>10}{kind_rejected:>10}{rate:>15}")
    else:
        lines.append("No accepted or rejected events in this window.")
    lines.append("")

    lines.append("Rejected by reason:")
    if rejected:
        reason_counts = Counter(e.fields["reason"] for e in rejected)
        for reason, count in reason_counts.most_common():
            lines.append(f"  {reason:<18}: {count}")
    else:
        lines.append("  (none)")

    return "\n".join(lines)


class Command(BaseCommand):
    help = (
        "Summarizes the receipt-QR decode path (apps/bot/handlers.py, apps/bot/qr.py) "
        "from apps.bot's structured logs, for a given time window."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default=None,
            help="Log file to read. Defaults to stdin, e.g. "
            "`docker compose logs web worker | python manage.py receipt_qr_report`.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Size of the reporting window, ending now (UTC). Default: 7.",
        )

    def handle(self, *args, **options):
        until = datetime.now(UTC).replace(tzinfo=None)
        since = until - timedelta(days=options["days"])

        path = options["file"]
        if path:
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        else:
            lines = sys.stdin.readlines()

        events = [e for e in parse_lines(lines) if since <= e.timestamp <= until]
        self.stdout.write(build_report(events, since=since, until=until))
