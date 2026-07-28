from decimal import Decimal

import pytest

from apps.bot.services import (
    RedeemAmountError,
    customer_is_registered,
    format_balance_message,
    format_notification_text,
    handle_balance_query,
    handle_redeem_request,
    handle_registration,
    handle_report,
    normalize_telegram_phone,
)
from apps.customers.models import OTP, Customer
from apps.ledger.services import post_earn_by_phone, post_earn_transaction


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("998901234567", "+998901234567"),
        ("+998901234567", "+998901234567"),
        (" 998901234567 ", "+998901234567"),
    ],
)
def test_normalize_telegram_phone(raw, expected):
    assert normalize_telegram_phone(raw) == expected


@pytest.mark.django_db
def test_handle_registration_creates_a_new_customer_and_claims_pending_cashback(
    make_tenant, make_branch, make_seller
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    post_earn_by_phone(
        tenant=tenant,
        branch=branch,
        seller=seller,
        phone="+998901234567",
        check_amount=Decimal("100000"),
        idempotency_key="pre-reg",
    )

    text = handle_registration(
        tenant=tenant, telegram_id=555, phone="998901234567", full_name="Aziz"
    )

    customer = Customer.objects.all_tenants().get(tenant=tenant, phone="+998901234567")
    assert customer.telegram_id == 555
    assert "registered" in text.lower()
    assert "10000.00" in text  # claimed amount mentioned
    assert "Your balance: 10000.00" in text


@pytest.mark.django_db
def test_handle_registration_is_idempotent_for_the_same_telegram_user(make_tenant):
    tenant = make_tenant("t")
    handle_registration(tenant=tenant, telegram_id=555, phone="998900000001", full_name="Aziz")
    handle_registration(tenant=tenant, telegram_id=555, phone="998900000001", full_name="Aziz")

    assert Customer.objects.all_tenants().filter(tenant=tenant, phone="+998900000001").count() == 1


@pytest.mark.django_db
def test_handle_balance_query_for_unregistered_user(make_tenant):
    tenant = make_tenant("t")
    text = handle_balance_query(tenant=tenant, telegram_id=999)
    assert "not registered" in text.lower()


@pytest.mark.django_db
def test_handle_balance_query_for_registered_user(make_tenant, make_branch, make_seller):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    handle_registration(tenant=tenant, telegram_id=555, phone="998900000001", full_name="Aziz")
    customer = Customer.objects.all_tenants().get(tenant=tenant, telegram_id=555)
    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )

    text = format_balance_message(customer)
    assert "10000.00" in text
    assert handle_balance_query(tenant=tenant, telegram_id=555) == text


@pytest.mark.django_db
def test_customer_is_registered(make_tenant):
    tenant = make_tenant("t")
    assert customer_is_registered(tenant=tenant, telegram_id=1) is False
    handle_registration(tenant=tenant, telegram_id=1, phone="998900000001", full_name="Aziz")
    assert customer_is_registered(tenant=tenant, telegram_id=1) is True


@pytest.mark.django_db
def test_handle_redeem_request_creates_an_otp_within_balance(
    make_tenant, make_branch, make_seller
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    handle_registration(tenant=tenant, telegram_id=555, phone="998900000001", full_name="Aziz")
    customer = Customer.objects.all_tenants().get(tenant=tenant, telegram_id=555)
    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("1000000"),
        idempotency_key="k1",
    )

    text = handle_redeem_request(tenant=tenant, telegram_id=555, raw_amount="20000")

    assert "Your code:" in text
    otp = OTP.objects.all_tenants().get(tenant=tenant, customer=customer)
    assert otp.amount_requested == Decimal("20000")
    assert str(otp.code) in text


@pytest.mark.django_db
def test_handle_redeem_request_rejects_amount_above_balance(make_tenant):
    tenant = make_tenant("t")
    handle_registration(tenant=tenant, telegram_id=555, phone="998900000001", full_name="Aziz")

    text = handle_redeem_request(tenant=tenant, telegram_id=555, raw_amount="50000")

    assert "don't have that many points" in text
    assert not OTP.objects.all_tenants().filter(tenant=tenant).exists()


@pytest.mark.django_db
def test_handle_redeem_request_rejects_garbage_input(make_tenant):
    tenant = make_tenant("t")
    handle_registration(tenant=tenant, telegram_id=555, phone="998900000001", full_name="Aziz")

    text = handle_redeem_request(tenant=tenant, telegram_id=555, raw_amount="not a number")

    assert "valid number" in text.lower()


def test_redeem_amount_error_is_a_plain_exception():
    with pytest.raises(RedeemAmountError):
        raise RedeemAmountError("nope")


@pytest.mark.django_db
def test_format_notification_text_for_an_earn_only_transaction(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    txn = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )

    text = format_notification_text(txn)

    assert "10000.00 points added" in text
    assert "Balance: 10000.00" in text


@pytest.mark.django_db
def test_handle_report_flags_the_reporting_customers_own_transaction(
    make_tenant, make_branch, make_seller, make_customer
):
    from apps.ledger.models import Transaction

    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    customer.telegram_id = 777
    customer.save(update_fields=["telegram_id"])
    txn = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )

    text = handle_report(tenant=tenant, telegram_id=777, transaction_id=txn.pk)

    assert "noted" in text.lower()
    assert Transaction.objects.all_tenants().get(pk=txn.pk).flagged is True


@pytest.mark.django_db
def test_handle_report_rejects_a_transaction_belonging_to_someone_else(
    make_tenant, make_branch, make_seller, make_customer
):
    from apps.ledger.models import Transaction

    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    customer.telegram_id = 777
    customer.save(update_fields=["telegram_id"])
    txn = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )

    text = handle_report(tenant=tenant, telegram_id=999, transaction_id=txn.pk)

    assert "could not be processed" in text
    assert Transaction.objects.all_tenants().get(pk=txn.pk).flagged is False


@pytest.mark.django_db
def test_handle_report_rejects_a_nonexistent_transaction_id(make_tenant):
    tenant = make_tenant("t")
    text = handle_report(tenant=tenant, telegram_id=777, transaction_id=999999)
    assert "could not be processed" in text
