import io
import statistics
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from django.core.management import call_command

from apps.bot.management.commands.receipt_qr_report import (
    ReceiptQrEvent,
    build_report,
    parse_line,
    parse_lines,
)

# --------------------------------------------------------------- parse_line


def test_parse_line_accepted():
    line = (
        "2026-08-18T13:05:07.536Z INFO apps.bot.handlers "
        "receipt_qr_accepted upload_kind=photo strategy=plain size_px=145"
    )
    event = parse_line(line)
    assert event is not None
    assert event.name == "receipt_qr_accepted"
    assert event.fields == {"upload_kind": "photo", "strategy": "plain", "size_px": "145"}
    assert event.timestamp == datetime(2026, 8, 18, 13, 5, 7, 536000)


def test_parse_line_rejected():
    line = (
        "2026-08-18T13:05:07.536Z WARNING apps.bot.handlers "
        "receipt_qr_rejected upload_kind=document reason=not_found "
        "detail='tried 4 strategies on 1280x1600'"
    )
    event = parse_line(line)
    assert event is not None
    assert event.name == "receipt_qr_rejected"
    assert event.fields["upload_kind"] == "document"
    assert event.fields["reason"] == "not_found"
    # %r-encoded on the way out -- parse_line must decode it back to a plain
    # string, not leave the surrounding quotes in.
    assert event.fields["detail"] == "tried 4 strategies on 1280x1600"


def test_parse_line_untrusted():
    line = (
        "2026-08-18T13:05:07.536Z WARNING apps.bot.handlers "
        "receipt_qr_untrusted upload_kind=photo "
        "raw_value='https://ofd.soliq.uz/epi?t=X&r=1&c=2&s=3'"
    )
    event = parse_line(line)
    assert event is not None
    assert event.name == "receipt_qr_untrusted"
    assert event.fields["raw_value"] == "https://ofd.soliq.uz/epi?t=X&r=1&c=2&s=3"


def test_parse_line_decodes_an_embedded_newline_in_a_repr_field():
    # A QR code is attacker-controlled input and could contain a literal
    # newline -- apps/bot/handlers.py logs raw_value with %r specifically so
    # this stays one physical log line (see that log call's own comment).
    # parse_line must recover the real (embedded-newline) string, not the
    # escaped "\n" two-character sequence.
    raw_with_newline = "evil\npayload"
    line = (
        f"2026-08-18T13:05:07.536Z WARNING apps.bot.handlers "
        f"receipt_qr_untrusted upload_kind=photo raw_value={raw_with_newline!r}"
    )
    assert "\n" not in line  # sanity: repr() really did keep this one physical line
    event = parse_line(line)
    assert event is not None
    assert event.fields["raw_value"] == raw_with_newline


def test_parse_line_tolerates_a_docker_compose_service_prefix():
    line = (
        "web-1  | 2026-08-18T13:05:07.536Z INFO apps.bot.handlers "
        "receipt_qr_accepted upload_kind=photo strategy=plain size_px=145"
    )
    event = parse_line(line)
    assert event is not None
    assert event.name == "receipt_qr_accepted"


@pytest.mark.parametrize(
    "line",
    [
        "",
        "garbage garbage garbage\n",
        "2026-08-18T13:05:07.536Z INFO django.request GET /api/health 200\n",
        "2026-08-18T13:05:07.536Z INFO apps.bot.qr receipt_qr_decode_success "
        "strategy=plain size_px=145 source=1280x1600 frame=1280x1600\n",
    ],
)
def test_parse_line_returns_none_for_non_matching_lines(line):
    # The last case is real (apps.bot.qr's own decode-level log line) --
    # this report is only about the three apps.bot.handlers events, and must
    # not misparse a similarly-named-but-different line from elsewhere.
    assert parse_line(line) is None


def test_parse_lines_filters_out_non_matching_lines():
    lines = [
        "garbage\n",
        "2026-08-18T13:05:07.536Z INFO apps.bot.handlers "
        "receipt_qr_accepted upload_kind=photo strategy=plain size_px=145\n",
        "also garbage\n",
    ]
    events = parse_lines(lines)
    assert len(events) == 1
    assert events[0].name == "receipt_qr_accepted"


# -------------------------------------------------------------- build_report


def _event(name, minutes_ago=0, **fields):
    return ReceiptQrEvent(
        timestamp=datetime(2026, 8, 18, 12, 0, 0) - timedelta(minutes=minutes_ago),
        name=name,
        fields=fields,
    )


def test_build_report_untrusted_rate_and_paths():
    events = [
        _event("receipt_qr_accepted", upload_kind="photo", strategy="plain", size_px="120"),
        _event("receipt_qr_accepted", upload_kind="photo", strategy="plain", size_px="130"),
        _event(
            "receipt_qr_untrusted",
            upload_kind="photo",
            raw_value="https://ofd.soliq.uz/epi?t=X&r=1&c=2&s=3",
        ),
    ]
    report = build_report(events, since=datetime(2026, 8, 11), until=datetime(2026, 8, 18))

    assert "receipt_qr_untrusted: 1 (33.3% of 3 successful decodes: 1 untrusted + 2 accepted)" in (
        report
    )
    assert "/epi" in report


def test_build_report_size_px_stats_and_histogram():
    sizes = [80, 95, 100, 105, 150, 250]
    events = [
        _event("receipt_qr_accepted", upload_kind="photo", strategy="plain", size_px=str(s))
        for s in sizes
    ]
    report = build_report(events, since=datetime(2026, 8, 11), until=datetime(2026, 8, 18))

    assert "accepted: 6" in report
    assert f"median: {statistics.median(sizes):.0f}px" in report
    # 80 -> "<90", 95/100/105 -> "90-109", 150 -> "130-159", 250 -> "200+"
    assert "<90     :    1" in report
    assert "90-109  :    3" in report
    assert "130-159 :    1" in report
    assert "200+    :    1" in report


def test_build_report_flags_a_median_near_the_decode_floor():
    events = [
        _event("receipt_qr_accepted", upload_kind="photo", strategy="plain", size_px="92")
        for _ in range(5)
    ]
    report = build_report(events, since=datetime(2026, 8, 11), until=datetime(2026, 8, 18))
    assert "scraping through" in report


def test_build_report_upload_kind_split_and_success_rate():
    events = (
        [
            _event("receipt_qr_accepted", upload_kind="photo", strategy="plain", size_px="120")
            for _ in range(3)
        ]
        + [_event("receipt_qr_rejected", upload_kind="photo", reason="not_found", detail="x")]
        + [
            _event("receipt_qr_accepted", upload_kind="document", strategy="plain", size_px="200")
            for _ in range(4)
        ]
        + [
            _event(
                "receipt_qr_rejected", upload_kind="document", reason="image_too_large", detail="x"
            )
        ]
    )
    report = build_report(events, since=datetime(2026, 8, 11), until=datetime(2026, 8, 18))

    # photo: 3 accepted, 1 rejected -> 75.0%; document: 4 accepted, 1 rejected -> 80.0%
    assert "photo" in report and "75.0%" in report
    assert "document" in report and "80.0%" in report
    assert "not_found" in report
    assert "image_too_large" in report


def test_build_report_handles_an_empty_window_without_crashing():
    report = build_report([], since=datetime(2026, 8, 11), until=datetime(2026, 8, 18))
    assert "0 accepted, 0 rejected, 0 untrusted" in report
    assert "No accepted decodes in this window." in report
    assert "(none)" in report


# --------------------------------------------------------------- the command


def _log_line(dt: datetime, event: str) -> str:
    ts = dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"
    return f"{ts} INFO apps.bot.handlers {event}"


def test_command_reads_from_a_file_and_respects_the_days_window(tmp_path):
    now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    recent = now - timedelta(hours=1)
    old = now - timedelta(days=30)

    log_path = tmp_path / "receipts.log"
    log_path.write_text(
        "\n".join(
            [
                _log_line(
                    recent,
                    "receipt_qr_accepted upload_kind=photo strategy=plain size_px=145",
                ),
                _log_line(
                    old,
                    "receipt_qr_accepted upload_kind=photo strategy=plain size_px=999",
                ),
                "not a log line at all",
            ]
        )
        + "\n"
    )

    out = io.StringIO()
    call_command("receipt_qr_report", f"--file={log_path}", "--days=7", stdout=out)
    report = out.getvalue()

    assert "1 accepted, 0 rejected, 0 untrusted" in report
    assert "median: 145px" in report
    assert "999" not in report  # the 30-day-old event must be excluded by the window


def test_command_reads_from_stdin_when_no_file_given():
    now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    line = _log_line(now, "receipt_qr_accepted upload_kind=document strategy=plain size_px=200")

    out = io.StringIO()
    with patch("sys.stdin", io.StringIO(line + "\n")):
        call_command("receipt_qr_report", stdout=out)
    report = out.getvalue()

    assert "1 accepted, 0 rejected, 0 untrusted" in report
    assert "document" in report


def test_command_default_window_is_seven_days(tmp_path):
    log_path = tmp_path / "receipts.log"
    log_path.write_text("")

    out = io.StringIO()
    call_command("receipt_qr_report", f"--file={log_path}", stdout=out)
    assert "(7 days)" in out.getvalue()
