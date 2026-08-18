"""Guards config.settings.LOGGING's "apps" entry (see that file's own
comment): every apps.* module's logger must resolve, through the logger
hierarchy, to at least one handler at INFO or lower — the exact bug that
left apps.bot.handlers' receipt_qr_accepted (INFO) silently dropped before
"apps.bot" got its own handler, and that a hand-maintained per-app list
would keep reproducing for every app nobody remembered to add.
"""

import logging
from pathlib import Path

import pytest
from django.conf import settings


def _reachable_handlers(logger: logging.Logger) -> list[logging.Handler]:
    """Every handler logging.Logger.callHandlers would actually walk past
    for a record from this logger — logger.handlers alone only holds
    handlers attached directly to it, not inherited ones."""
    handlers: list[logging.Handler] = []
    current: logging.Logger | None = logger
    while current is not None:
        handlers.extend(current.handlers)
        if not current.propagate:
            break
        current = current.parent
    return handlers


def _apps_module_names() -> list[str]:
    """Every real apps.* module in this project, derived from the file tree
    (not from importing anything, so this can't accidentally trigger
    app-loading side effects) — apps/ledger/tasks.py -> "apps.ledger.tasks",
    apps/bot/__init__.py -> "apps.bot"."""
    apps_dir = Path(settings.BASE_DIR) / "apps"
    names = set()
    for path in apps_dir.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        module_path = path.parent if path.name == "__init__.py" else path.with_suffix("")
        rel = module_path.relative_to(settings.BASE_DIR)
        names.add(".".join(rel.parts))
    return sorted(names)


@pytest.mark.parametrize("logger_name", _apps_module_names())
def test_every_real_apps_module_logger_has_an_info_level_handler(logger_name):
    logger = logging.getLogger(logger_name)
    assert logger.getEffectiveLevel() <= logging.INFO, (
        f"{logger_name}'s effective level is "
        f"{logging.getLevelName(logger.getEffectiveLevel())}, not INFO or lower"
    )
    assert _reachable_handlers(logger), f"{logger_name} has no reachable handler at all"


@pytest.mark.parametrize(
    "logger_name",
    [
        # None of these modules exist -- the point (per this test file's own
        # docstring) is that config.settings.LOGGING's "apps" entry is a
        # hierarchy rule, not a list of today's apps. A brand new app added
        # tomorrow must be covered without anyone touching LOGGING again.
        "apps.a_brand_new_app_nobody_has_written_yet",
        "apps.a_brand_new_app_nobody_has_written_yet.tasks",
        "apps.ledger.some_module_added_next_sprint",
    ],
)
def test_a_hypothetical_future_apps_module_is_covered_too(logger_name):
    logger = logging.getLogger(logger_name)
    assert logger.getEffectiveLevel() <= logging.INFO
    assert _reachable_handlers(logger)


def test_apps_logger_handler_scope_excludes_django():
    """Confirms the "apps" entry is scoped to this project's own code, not
    Django's — a handler this broad (matching django.* too) would risk
    double-printing every Django request log through both the "django" and
    "apps" configs at once."""
    django_logger = logging.getLogger("django.request")
    apps_logger = logging.getLogger("apps")

    apps_handlers = set(_reachable_handlers(apps_logger))
    django_handlers = set(_reachable_handlers(django_logger))
    assert apps_handlers.isdisjoint(django_handlers)


def test_apps_dot_bot_no_longer_has_its_own_handler_entry():
    """Regression test for the fix itself: an "apps.bot"-specific logger
    entry left in place alongside the new "apps" one would give every
    apps.bot.* record two real (non-caplog) handlers instead of one — see
    test_apps_bot_logger_has_exactly_one_real_handler below for that
    structural check, and test_a_single_log_call_produces_exactly_one_record
    for the direct behavioral one."""
    assert "apps.bot" not in settings.LOGGING["loggers"]


def test_apps_bot_logger_has_exactly_one_real_handler():
    """Structural version of "no duplicate line": counts actual
    logging.StreamHandler instances reachable from apps.bot.qr, which is
    what would double if a leftover "apps.bot" entry sat alongside "apps" —
    two distinct StreamHandlers each format and print their own line, so
    this is the number of lines one log call would actually produce.
    caplog's own capture handler doesn't count here (it isn't a plain
    StreamHandler), which is exactly why this needs a separate structural
    check and not just a caplog record count (caplog only ever adds itself
    once, so it can't see a duplicate among the OTHER handlers)."""
    handlers = _reachable_handlers(logging.getLogger("apps.bot.qr"))
    real_handlers = [h for h in handlers if type(h) is logging.StreamHandler]
    assert len(real_handlers) == 1


def test_a_single_log_call_produces_exactly_one_record(caplog):
    caplog.set_level("INFO", logger="apps.bot.qr")
    logging.getLogger("apps.bot.qr").info(
        "test_a_single_log_call_produces_exactly_one_record marker"
    )
    matching = [r for r in caplog.records if "marker" in r.message]
    assert len(matching) == 1
