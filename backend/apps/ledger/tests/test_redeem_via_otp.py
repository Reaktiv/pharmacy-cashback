from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.customers.models import OTP
from apps.ledger.services import (
    InvalidOTPError,
    get_balance,
    post_earn_transaction,
    redeem_via_otp,
)


def _seed_balance(tenant, branch, seller, customer, amount_check=Decimal("1000000")):
    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=amount_check,
        idempotency_key="seed",
    )


@pytest.mark.django_db
def test_redeem_via_otp_posts_a_spend_and_marks_otp_used(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    _seed_balance(tenant, branch, seller, customer)  # balance = 100000

    otp = OTP.objects.all_tenants().create(
        tenant=tenant, customer=customer, code="123456", amount_requested=Decimal("40000")
    )

    txn = redeem_via_otp(
        tenant=tenant,
        branch=branch,
        seller=seller,
        otp_code="123456",
        check_amount=Decimal("100000"),
        idempotency_key="redeem-1",
    )

    assert txn.cashback_spent == Decimal("40000")
    otp.refresh_from_db()
    assert otp.used is True
    assert get_balance(customer) == Decimal("100000.00") - Decimal("40000") + txn.cashback_earned


@pytest.mark.django_db
def test_redeem_via_otp_respects_the_50_percent_cap_even_if_more_was_requested(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    _seed_balance(tenant, branch, seller, customer)  # balance = 100000

    OTP.objects.all_tenants().create(
        tenant=tenant, customer=customer, code="123456", amount_requested=Decimal("100000")
    )

    txn = redeem_via_otp(
        tenant=tenant,
        branch=branch,
        seller=seller,
        otp_code="123456",
        check_amount=Decimal("100000"),  # cap = 50000
        idempotency_key="redeem-1",
    )

    assert txn.cashback_spent == Decimal("50000")


@pytest.mark.django_db
def test_redeem_via_otp_rejects_unknown_code(make_tenant, make_branch, make_seller):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)

    with pytest.raises(InvalidOTPError):
        redeem_via_otp(
            tenant=tenant,
            branch=branch,
            seller=seller,
            otp_code="000000",
            check_amount=Decimal("100000"),
            idempotency_key="redeem-1",
        )


@pytest.mark.django_db
def test_redeem_via_otp_rejects_an_already_used_otp(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)

    OTP.objects.all_tenants().create(
        tenant=tenant,
        customer=customer,
        code="123456",
        amount_requested=Decimal("10000"),
        used=True,
    )

    with pytest.raises(InvalidOTPError):
        redeem_via_otp(
            tenant=tenant,
            branch=branch,
            seller=seller,
            otp_code="123456",
            check_amount=Decimal("100000"),
            idempotency_key="redeem-1",
        )


@pytest.mark.django_db
def test_redeem_via_otp_rejects_an_expired_otp(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)

    OTP.objects.all_tenants().create(
        tenant=tenant,
        customer=customer,
        code="123456",
        amount_requested=Decimal("10000"),
        expires_at=timezone.now() - timedelta(minutes=1),
    )

    with pytest.raises(InvalidOTPError):
        redeem_via_otp(
            tenant=tenant,
            branch=branch,
            seller=seller,
            otp_code="123456",
            check_amount=Decimal("100000"),
            idempotency_key="redeem-1",
        )


@pytest.mark.django_db
def test_redeem_via_otp_from_a_different_tenant_is_rejected(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant_a = make_tenant("a")
    branch_a = make_branch(tenant_a)
    seller_a = make_seller(tenant_a, branch_a)

    tenant_b = make_tenant("b")
    make_branch(tenant_b)
    customer_b = make_customer(tenant_b)
    OTP.objects.all_tenants().create(
        tenant=tenant_b, customer=customer_b, code="123456", amount_requested=Decimal("10000")
    )

    with pytest.raises(InvalidOTPError):
        redeem_via_otp(
            tenant=tenant_a,
            branch=branch_a,
            seller=seller_a,
            otp_code="123456",
            check_amount=Decimal("100000"),
            idempotency_key="redeem-1",
        )


@pytest.mark.django_db
def test_redeem_via_otp_below_minimum_check_amount_is_rejected(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t")
    tenant.min_redeem_amount = Decimal("20000.00")
    tenant.save()
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    _seed_balance(tenant, branch, seller, customer)

    OTP.objects.all_tenants().create(
        tenant=tenant, customer=customer, code="123456", amount_requested=Decimal("5000")
    )

    with pytest.raises(InvalidOTPError):
        redeem_via_otp(
            tenant=tenant,
            branch=branch,
            seller=seller,
            otp_code="123456",
            check_amount=Decimal("10000"),  # below the 20000 minimum
            idempotency_key="redeem-1",
        )
