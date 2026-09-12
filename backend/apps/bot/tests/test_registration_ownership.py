"""Audit finding C-2: a Telegram account may only register a phone number
it has proved it owns, and a Customer row that is already claimed must
never be reassigned to a different account.

Two independent defects sat behind this, so there are two layers of test:

* `on_contact` (apps/bot/handlers.py) — the ownership *proof*. It used to
  accept a contact whose `user_id` was None, which is what Telegram sends
  for a forwarded address-book contact, so anyone could assert any number.
  Driven here through the real webhook, because the guard only exists on
  that path.
* `handle_registration` (apps/bot/services.py) — the ownership *binding*.
  It used to overwrite `Customer.telegram_id` on any row whose id didn't
  match, moving that customer's whole ledger balance onto the caller.

Each test uses its own telegram/chat ids: FSM state lives in a real Redis
that Django's per-test rollback does not touch.
"""

import threading
from decimal import Decimal

import pytest
from aiogram import Bot as AiogramBot
from django.db import connection

from apps.bot.services import RegistrationOwnershipError, handle_registration
from apps.customers.models import Customer
from apps.ledger.services import get_balance, post_earn_by_phone
from apps.tenants.models import Bot as BotRow

VICTIM_PHONE = "+998901234567"


# --------------------------------------------------------------- fixtures


@pytest.fixture
def shop(make_tenant, make_branch, make_seller):
    tenant = make_tenant("ownershop", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    row = BotRow.objects.all_tenants().create(tenant=tenant, username="@ownershop_bot")
    row.set_token("123456:FAKE-TOKEN-FOR-TESTS")
    row.save()
    return {"row": row, "tenant": tenant, "branch": branch, "seller": seller}


@pytest.fixture(autouse=True)
def mock_outbound_telegram():
    """Same interception point as test_webhook_view.py: every Bot API call
    funnels through Bot.__call__."""
    calls = []

    async def fake_call(self, method, request_timeout=None):
        calls.append(method)
        return None

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(AiogramBot, "__call__", fake_call)
        yield calls


def _sent_texts(calls):
    return [c.text for c in calls if c.__class__.__name__ == "SendMessage"]


def _post(client, row, payload):
    return client.post(
        f"/webhook/{row.webhook_secret}/", data=payload, content_type="application/json"
    )


def _contact_update(update_id, user_id, contact):
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 1234567890,
            "chat": {"id": user_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Mallory"},
            "contact": contact,
        },
    }


# ------------------------------------------- C-2a: proving phone ownership


@pytest.mark.django_db
def test_contact_without_user_id_cannot_claim_a_phone_number(client, shop, mock_outbound_telegram):
    """The core C-2a regression. Telegram omits `user_id` on a contact that
    isn't itself a Telegram account — a forwarded address-book card — and
    the old `contact.user_id and ...` guard short-circuited to *pass* on
    exactly that shape."""
    attacker_id = 700001

    _post(
        client,
        shop["row"],
        _contact_update(
            1,
            user_id=attacker_id,
            # No "user_id" key at all: an address-book contact.
            contact={"phone_number": VICTIM_PHONE, "first_name": "Someone Else"},
        ),
    )

    texts = _sent_texts(mock_outbound_telegram)
    assert texts, "handler sent nothing"
    assert "o'zingizning kontaktingizni" in texts[-1], texts
    # And crucially: the flow must not have advanced to the consent step.
    assert not any("rozilik" in text for text in texts), texts


@pytest.mark.django_db
def test_contact_with_a_mismatched_user_id_is_still_rejected(
    client, shop, mock_outbound_telegram
):
    """The case the old guard did cover — kept so the fix can't regress it
    while fixing the None case."""
    _post(
        client,
        shop["row"],
        _contact_update(
            1,
            user_id=700002,
            contact={"phone_number": VICTIM_PHONE, "first_name": "V", "user_id": 999999},
        ),
    )

    texts = _sent_texts(mock_outbound_telegram)
    assert "o'zingizning kontaktingizni" in texts[-1], texts


@pytest.mark.django_db
def test_own_verified_contact_is_still_accepted(client, shop, mock_outbound_telegram):
    """The legitimate path: the request_contact button always returns the
    sender's own contact, with user_id == their id. Must keep working."""
    user_id = 700003

    _post(
        client,
        shop["row"],
        _contact_update(
            1,
            user_id=user_id,
            contact={"phone_number": VICTIM_PHONE, "first_name": "Aziz", "user_id": user_id},
        ),
    )

    texts = _sent_texts(mock_outbound_telegram)
    # Reached the consent step rather than being rejected.
    assert any("rozilik" in text for text in texts), texts
    assert not any("o'zingizning kontaktingizni" in text for text in texts), texts


# --------------------------------------- C-2b: binding the Telegram account


@pytest.mark.django_db
def test_an_already_claimed_customer_cannot_be_reassigned(shop):
    """The takeover itself: victim registers and earns, attacker submits
    the same phone. Before the fix this moved the row — and the balance —
    onto the attacker's telegram_id."""
    tenant, branch, seller = shop["tenant"], shop["branch"], shop["seller"]

    handle_registration(tenant=tenant, telegram_id=1001, phone=VICTIM_PHONE, full_name="Victim")
    post_earn_by_phone(
        tenant=tenant,
        branch=branch,
        seller=seller,
        phone=VICTIM_PHONE,
        check_amount=Decimal("500000"),
        idempotency_key="v1",
    )
    victim = Customer.objects.all_tenants().get(tenant=tenant, phone=VICTIM_PHONE)
    assert get_balance(victim) == Decimal("50000.00")

    with pytest.raises(RegistrationOwnershipError):
        handle_registration(
            tenant=tenant, telegram_id=666, phone=VICTIM_PHONE, full_name="Mallory"
        )

    victim.refresh_from_db()
    assert victim.telegram_id == 1001
    assert victim.full_name == "Victim"
    assert get_balance(victim) == Decimal("50000.00")
    # The attacker has no customer row in this tenant at all.
    assert not Customer.objects.all_tenants().filter(tenant=tenant, telegram_id=666).exists()


@pytest.mark.django_db
def test_pending_cashback_cannot_be_stolen_through_registration(shop):
    """Cashback accrued at the till for a not-yet-registered phone is the
    other half of C-2: with the contact guard fixed an attacker can no
    longer assert the number, and if they somehow reach the service with a
    phone already bound elsewhere they are refused before
    claim_pending_cashback runs."""
    tenant, branch, seller = shop["tenant"], shop["branch"], shop["seller"]

    post_earn_by_phone(
        tenant=tenant,
        branch=branch,
        seller=seller,
        phone=VICTIM_PHONE,
        check_amount=Decimal("500000"),
        idempotency_key="p1",
    )
    # The rightful owner registers first and receives the pending amount.
    handle_registration(tenant=tenant, telegram_id=1001, phone=VICTIM_PHONE, full_name="Victim")
    owner = Customer.objects.all_tenants().get(tenant=tenant, telegram_id=1001)
    assert get_balance(owner) == Decimal("50000.00")

    with pytest.raises(RegistrationOwnershipError):
        handle_registration(
            tenant=tenant, telegram_id=666, phone=VICTIM_PHONE, full_name="Mallory"
        )

    owner.refresh_from_db()
    assert get_balance(owner) == Decimal("50000.00")
    assert not Customer.objects.all_tenants().filter(tenant=tenant, telegram_id=666).exists()


@pytest.mark.django_db
def test_an_unclaimed_customer_row_can_still_be_claimed(shop):
    """Must keep working: a Customer created without a telegram_id (Django
    admin, seed_demo_data) is claimed by the first account that registers
    it, along with any pending cashback for that phone."""
    tenant, branch, seller = shop["tenant"], shop["branch"], shop["seller"]

    Customer.objects.all_tenants().create(
        tenant=tenant, phone=VICTIM_PHONE, full_name="Walk-in"
    )
    post_earn_by_phone(
        tenant=tenant,
        branch=branch,
        seller=seller,
        phone=VICTIM_PHONE,
        check_amount=Decimal("500000"),
        idempotency_key="u1",
    )

    text = handle_registration(
        tenant=tenant, telegram_id=1001, phone=VICTIM_PHONE, full_name="Aziz"
    )

    customer = Customer.objects.all_tenants().get(tenant=tenant, phone=VICTIM_PHONE)
    assert customer.telegram_id == 1001
    assert customer.full_name == "Aziz"
    assert customer.consent_given_at is not None
    assert get_balance(customer) == Decimal("50000.00")
    assert "ro'yxatdan o'tdingiz" in text.lower()


@pytest.mark.django_db
def test_first_time_registration_still_works(shop):
    """No pre-existing row at all — the ordinary happy path."""
    tenant = shop["tenant"]

    text = handle_registration(
        tenant=tenant, telegram_id=1001, phone="998907654321", full_name="Aziz"
    )

    customer = Customer.objects.all_tenants().get(tenant=tenant, telegram_id=1001)
    assert customer.phone == "+998907654321"
    assert customer.full_name == "Aziz"
    assert customer.consent_given_at is not None
    assert "ro'yxatdan o'tdingiz" in text.lower()


@pytest.mark.django_db
def test_re_registering_the_same_phone_is_idempotent(shop):
    """A double-tapped consent button, or a customer re-running /start,
    must stay a no-op rather than being refused as a takeover."""
    tenant = shop["tenant"]

    handle_registration(tenant=tenant, telegram_id=1001, phone=VICTIM_PHONE, full_name="Aziz")
    handle_registration(tenant=tenant, telegram_id=1001, phone=VICTIM_PHONE, full_name="Aziz")
    text = handle_registration(
        tenant=tenant, telegram_id=1001, phone=VICTIM_PHONE, full_name="Aziz"
    )

    assert Customer.objects.all_tenants().filter(tenant=tenant, phone=VICTIM_PHONE).count() == 1
    customer = Customer.objects.all_tenants().get(tenant=tenant, phone=VICTIM_PHONE)
    assert customer.telegram_id == 1001
    assert "ro'yxatdan o'tdingiz" in text.lower()


@pytest.mark.django_db
def test_pending_cashback_is_only_credited_once_across_repeat_registrations(shop):
    """Idempotency that actually matters financially: re-registering must
    not re-claim the same PendingCashback row."""
    tenant, branch, seller = shop["tenant"], shop["branch"], shop["seller"]

    post_earn_by_phone(
        tenant=tenant,
        branch=branch,
        seller=seller,
        phone=VICTIM_PHONE,
        check_amount=Decimal("500000"),
        idempotency_key="i1",
    )
    handle_registration(tenant=tenant, telegram_id=1001, phone=VICTIM_PHONE, full_name="Aziz")
    handle_registration(tenant=tenant, telegram_id=1001, phone=VICTIM_PHONE, full_name="Aziz")

    customer = Customer.objects.all_tenants().get(tenant=tenant, telegram_id=1001)
    assert get_balance(customer) == Decimal("50000.00")


@pytest.mark.django_db
def test_the_same_account_cannot_register_a_second_phone(shop):
    """`unique_customer_telegram_id_per_tenant` used to surface as an
    IntegrityError that the webhook swallowed into a silent 200. It is now
    checked explicitly and reported."""
    tenant = shop["tenant"]

    handle_registration(tenant=tenant, telegram_id=1001, phone=VICTIM_PHONE, full_name="Aziz")

    with pytest.raises(RegistrationOwnershipError):
        handle_registration(
            tenant=tenant, telegram_id=1001, phone="998900000009", full_name="Aziz"
        )

    assert Customer.objects.all_tenants().filter(tenant=tenant, telegram_id=1001).count() == 1


@pytest.mark.django_db
def test_registration_is_scoped_per_tenant(shop, make_tenant):
    """The same person is a separate customer at each pharmacy — the
    ownership rule must not leak across tenants and block that."""
    other = make_tenant("othershop", rate=Decimal("5.00"))

    handle_registration(
        tenant=shop["tenant"], telegram_id=1001, phone=VICTIM_PHONE, full_name="Aziz"
    )
    handle_registration(tenant=other, telegram_id=1001, phone=VICTIM_PHONE, full_name="Aziz")

    assert Customer.objects.all_tenants().filter(phone=VICTIM_PHONE, telegram_id=1001).count() == 2


# ------------------------------------------------------------- concurrency


@pytest.mark.django_db(transaction=True)
def test_concurrent_registrations_cannot_both_claim_the_same_phone(
    make_tenant, make_branch, make_seller
):
    """Two accounts consenting to the same phone at the same instant. With
    a plain read both could observe `telegram_id IS NULL` and both bind;
    the service takes `select_for_update` so the loser re-reads the
    committed winner and is refused.

    transaction=True is required: the threads need real committed
    transactions and their own connections, which the default wrapping
    transaction would not give them.
    """
    tenant = make_tenant("raceshop", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)

    # An unclaimed row holding real money — the takeover target.
    Customer.objects.all_tenants().create(tenant=tenant, phone=VICTIM_PHONE, full_name="Walk-in")
    post_earn_by_phone(
        tenant=tenant,
        branch=branch,
        seller=seller,
        phone=VICTIM_PHONE,
        check_amount=Decimal("500000"),
        idempotency_key="race1",
    )

    start = threading.Barrier(2)
    outcomes: list[tuple[int, str]] = []
    lock = threading.Lock()

    def attempt(telegram_id: int) -> None:
        try:
            start.wait(timeout=10)
            handle_registration(
                tenant=tenant,
                telegram_id=telegram_id,
                phone=VICTIM_PHONE,
                full_name=f"User{telegram_id}",
            )
            result = "claimed"
        except RegistrationOwnershipError:
            result = "refused"
        except Exception as exc:  # surfaced in the assertions below, never swallowed
            result = f"error:{type(exc).__name__}:{exc}"
        finally:
            connection.close()
        with lock:
            outcomes.append((telegram_id, result))

    threads = [
        threading.Thread(target=attempt, args=(1001,)),
        threading.Thread(target=attempt, args=(2002,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive(), "registration thread deadlocked"

    results = sorted(result for _, result in outcomes)
    assert results == ["claimed", "refused"], outcomes

    rows = list(Customer.objects.all_tenants().filter(tenant=tenant, phone=VICTIM_PHONE))
    assert len(rows) == 1
    winner_id = next(tid for tid, result in outcomes if result == "claimed")
    assert rows[0].telegram_id == winner_id
    # The money went to exactly one account, and all of it.
    assert get_balance(rows[0]) == Decimal("50000.00")


@pytest.mark.django_db
def test_a_raced_insert_still_goes_through_the_ownership_check(shop, monkeypatch):
    """Covers `handle_registration`'s `except IntegrityError` branch
    deterministically.

    The threaded tests only reach it if the scheduler happens to interleave
    that way, so this forces the exact window: `_assert_account_unclaimed`
    is the last thing to run before the INSERT on the no-existing-row path,
    so hooking it lets a competing row land in between. The INSERT then
    trips unique_customer_phone_per_tenant for real, and the recovery path
    must re-read the winner and refuse — not crash, and not overwrite.
    """
    from apps.bot import services as bot_services

    tenant = shop["tenant"]
    original = bot_services._assert_account_unclaimed
    raced = {"done": False}

    def assert_then_let_a_competitor_win(**kwargs):
        original(**kwargs)
        if not raced["done"]:
            raced["done"] = True
            Customer.objects.all_tenants().create(
                tenant=tenant, phone=VICTIM_PHONE, telegram_id=1001, full_name="Winner"
            )

    monkeypatch.setattr(
        bot_services, "_assert_account_unclaimed", assert_then_let_a_competitor_win
    )

    with pytest.raises(RegistrationOwnershipError):
        handle_registration(
            tenant=tenant, telegram_id=2002, phone=VICTIM_PHONE, full_name="Loser"
        )

    assert raced["done"], "the raced-insert branch was never reached"
    # The important part is *which* exception came out: RegistrationOwnershipError
    # (checked above) rather than the raw IntegrityError, or the
    # Customer.DoesNotExist that a naive `.get(phone=...)` recovery would
    # raise. The loser bound nothing.
    #
    # The competing row is gone here only because this test has to create
    # it inside handle_registration's own transaction to hit the window,
    # and the refusal rolls that transaction back. In production the
    # competitor commits separately and survives — what this asserts is the
    # other half of the same guarantee: a refused registration leaves
    # nothing behind at all.
    assert not Customer.objects.all_tenants().filter(tenant=tenant, telegram_id=2002).exists()
    assert not Customer.objects.all_tenants().filter(tenant=tenant, telegram_id=1001).exists()


@pytest.mark.django_db
def test_a_raced_insert_on_the_account_constraint_is_reported_not_crashed(shop, monkeypatch):
    """The other constraint that can fire in the same window.

    If the competing registration is this *same* Telegram account claiming
    a different phone, the INSERT trips unique_customer_telegram_id_per_tenant
    rather than the phone one — and then there is no row at `phone` to
    recover with. A recovery that assumed the phone constraint would raise
    Customer.DoesNotExist straight into the webhook's blanket handler,
    which turns it into a silent 200 and no reply at all. It must come out
    as the normal, translated refusal instead.
    """
    from apps.bot import services as bot_services

    tenant = shop["tenant"]
    original = bot_services._assert_account_unclaimed
    raced = {"done": False}

    def assert_then_let_the_same_account_win_elsewhere(**kwargs):
        original(**kwargs)
        if not raced["done"]:
            raced["done"] = True
            # Same telegram_id, a different phone.
            Customer.objects.all_tenants().create(
                tenant=tenant, phone="+998900000077", telegram_id=2002, full_name="Elsewhere"
            )

    monkeypatch.setattr(
        bot_services, "_assert_account_unclaimed", assert_then_let_the_same_account_win_elsewhere
    )

    with pytest.raises(RegistrationOwnershipError):
        handle_registration(
            tenant=tenant, telegram_id=2002, phone=VICTIM_PHONE, full_name="Loser"
        )

    assert raced["done"], "the raced-insert branch was never reached"
    assert not Customer.objects.all_tenants().filter(tenant=tenant, phone=VICTIM_PHONE).exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_first_time_registrations_do_not_double_create(
    make_tenant, make_branch, make_seller
):
    """Same race, but with no row existing yet, so both threads race on the
    INSERT instead of the UPDATE. The unique constraint decides; the loser
    must fall through to the ownership check, not crash and not duplicate.
    """
    tenant = make_tenant("raceshop2", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    post_earn_by_phone(
        tenant=tenant,
        branch=branch,
        seller=seller,
        phone=VICTIM_PHONE,
        check_amount=Decimal("500000"),
        idempotency_key="race2",
    )

    start = threading.Barrier(2)
    outcomes: list[tuple[int, str]] = []
    lock = threading.Lock()

    def attempt(telegram_id: int) -> None:
        try:
            start.wait(timeout=10)
            handle_registration(
                tenant=tenant,
                telegram_id=telegram_id,
                phone=VICTIM_PHONE,
                full_name=f"User{telegram_id}",
            )
            result = "claimed"
        except RegistrationOwnershipError:
            result = "refused"
        except Exception as exc:
            result = f"error:{type(exc).__name__}:{exc}"
        finally:
            connection.close()
        with lock:
            outcomes.append((telegram_id, result))

    threads = [
        threading.Thread(target=attempt, args=(1001,)),
        threading.Thread(target=attempt, args=(2002,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive(), "registration thread deadlocked"

    assert sorted(result for _, result in outcomes) == ["claimed", "refused"], outcomes

    rows = list(Customer.objects.all_tenants().filter(tenant=tenant, phone=VICTIM_PHONE))
    assert len(rows) == 1
    winner_id = next(tid for tid, result in outcomes if result == "claimed")
    assert rows[0].telegram_id == winner_id
    assert get_balance(rows[0]) == Decimal("50000.00")
