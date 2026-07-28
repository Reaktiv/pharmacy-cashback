from decimal import Decimal

import pytest

from apps.ledger.services import (
    DailyRedemptionLimitExceededError,
    DailyTransactionLimitExceededError,
    MaxCheckAmountExceededError,
    post_earn_by_phone,
    post_earn_transaction,
    redeem_via_otp,
)
from apps.tenants.models import GlobalSettings


@pytest.mark.django_db
def test_check_amount_above_global_max_is_rejected(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    settings = GlobalSettings.load()
    settings.max_check_amount = Decimal("100000.00")
    settings.save()

    with pytest.raises(MaxCheckAmountExceededError):
        post_earn_transaction(
            tenant=tenant,
            branch=branch,
            seller=seller,
            customer=customer,
            check_amount=Decimal("100001"),
            idempotency_key="k1",
        )


@pytest.mark.django_db
def test_check_amount_at_exactly_the_global_max_is_allowed(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    settings = GlobalSettings.load()
    settings.max_check_amount = Decimal("100000.00")
    settings.save()

    txn = post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("100000"),
        idempotency_key="k1",
    )
    assert txn.check_amount == Decimal("100000")


@pytest.mark.django_db
def test_max_check_amount_also_blocks_the_pending_cashback_path(
    make_tenant, make_branch, make_seller
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    settings = GlobalSettings.load()
    settings.max_check_amount = Decimal("100000.00")
    settings.save()

    with pytest.raises(MaxCheckAmountExceededError):
        post_earn_by_phone(
            tenant=tenant,
            branch=branch,
            seller=seller,
            phone="+998900000001",
            check_amount=Decimal("999999"),
            idempotency_key="k1",
        )


@pytest.mark.django_db
def test_seller_daily_txn_limit_uses_tenant_default_when_seller_has_none(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    tenant.default_daily_txn_limit = 2
    tenant.save()
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)

    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("10000"),
        idempotency_key="k1",
    )
    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("10000"),
        idempotency_key="k2",
    )

    with pytest.raises(DailyTransactionLimitExceededError):
        post_earn_transaction(
            tenant=tenant,
            branch=branch,
            seller=seller,
            customer=customer,
            check_amount=Decimal("10000"),
            idempotency_key="k3",
        )


@pytest.mark.django_db
def test_seller_specific_limit_overrides_tenant_default(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    tenant.default_daily_txn_limit = 1
    tenant.save()
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    seller.daily_txn_limit = 3
    seller.save()
    customer = make_customer(tenant)

    for i in range(3):
        post_earn_transaction(
            tenant=tenant,
            branch=branch,
            seller=seller,
            customer=customer,
            check_amount=Decimal("10000"),
            idempotency_key=f"k{i}",
        )

    with pytest.raises(DailyTransactionLimitExceededError):
        post_earn_transaction(
            tenant=tenant,
            branch=branch,
            seller=seller,
            customer=customer,
            check_amount=Decimal("10000"),
            idempotency_key="k-over",
        )


@pytest.mark.django_db
def test_no_daily_txn_limit_by_default(make_tenant, make_branch, make_seller, make_customer):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)

    for i in range(10):
        post_earn_transaction(
            tenant=tenant,
            branch=branch,
            seller=seller,
            customer=customer,
            check_amount=Decimal("10000"),
            idempotency_key=f"k{i}",
        )  # must not raise


@pytest.mark.django_db
def test_customer_daily_redemption_limit_is_enforced(
    make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant)
    settings = GlobalSettings.load()
    settings.max_daily_redemptions_per_customer = 2
    settings.save()

    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("1000000"),
        idempotency_key="seed",
    )

    from apps.customers.models import OTP

    for i in range(2):
        otp = OTP.objects.all_tenants().create(
            tenant=tenant, customer=customer, code=f"11111{i}", amount_requested=Decimal("1000")
        )
        redeem_via_otp(
            tenant=tenant,
            branch=branch,
            seller=seller,
            otp_code=otp.code,
            check_amount=Decimal("20000"),
            idempotency_key=f"redeem-{i}",
        )

    otp = OTP.objects.all_tenants().create(
        tenant=tenant, customer=customer, code="999999", amount_requested=Decimal("1000")
    )
    with pytest.raises(DailyRedemptionLimitExceededError):
        redeem_via_otp(
            tenant=tenant,
            branch=branch,
            seller=seller,
            otp_code=otp.code,
            check_amount=Decimal("20000"),
            idempotency_key="redeem-over",
        )
