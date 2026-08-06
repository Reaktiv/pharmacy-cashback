from decimal import Decimal

import pytest

from apps.accounts.models import UserProfile
from apps.customers.models import OTP
from apps.ledger.models import Transaction
from apps.ledger.services import get_balance, post_earn_transaction


@pytest.mark.django_db
def test_anonymous_user_is_redirected_to_login(client):
    response = client.get("/seller/")
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_non_seller_role_gets_forbidden(client, make_tenant, make_user):
    tenant = make_tenant("t")
    make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant, username="admin1")
    client.login(username="admin1", password="pass1234")

    response = client.get("/seller/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_seller_sees_the_register_page(client, make_tenant, make_branch, make_seller):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    client.login(username=seller.user.username, password="pass1234")

    response = client.get("/seller/")

    assert response.status_code == 200
    assert b"Sotuv" in response.content
    assert b"Ballarni ishlatish" in response.content


@pytest.mark.django_db
def test_register_page_renders_in_the_chosen_language(
    client, make_tenant, make_branch, make_seller
):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    client.login(username=seller.user.username, password="pass1234")
    client.cookies["seller_lang"] = "ru"

    response = client.get("/seller/")

    assert response.status_code == 200
    assert "Продажа".encode() in response.content
    assert "Использовать баллы".encode() in response.content
    assert "Выйти".encode() in response.content
    assert b"Sotuv" not in response.content


@pytest.mark.django_db
def test_forbidden_page_renders_in_the_chosen_language(client, make_tenant, make_user):
    tenant = make_tenant("t")
    make_user(role=UserProfile.Role.TENANT_ADMIN, tenant=tenant, username="admin1")
    client.login(username="admin1", password="pass1234")
    client.cookies["seller_lang"] = "en"

    response = client.get("/seller/")

    assert response.status_code == 403
    assert b"Not available" in response.content


@pytest.mark.django_db
def test_set_language_sets_the_cookie_and_redirects_back(
    client, make_tenant, make_branch, make_seller
):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    client.login(username=seller.user.username, password="pass1234")

    response = client.post("/seller/set-language/", {"language": "en", "next": "/seller/"})

    assert response.status_code == 302
    assert response.url == "/seller/"
    assert response.cookies["seller_lang"].value == "en"

    response = client.get("/seller/")
    assert b"Redeem points" in response.content


@pytest.mark.django_db
def test_set_language_ignores_an_unsafe_next_url(client):
    response = client.post(
        "/seller/set-language/", {"language": "en", "next": "https://evil.example/steal"}
    )

    assert response.status_code == 302
    assert response.url == "/"


@pytest.mark.django_db
def test_set_language_ignores_an_invalid_language(client):
    response = client.post("/seller/set-language/", {"language": "fr", "next": "/seller/"})

    assert response.status_code == 302
    assert "seller_lang" not in response.cookies


@pytest.mark.django_db
def test_earn_end_to_end_for_an_existing_customer(
    client, make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant, phone="+998900000001")
    client.login(username=seller.user.username, password="pass1234")

    response = client.post(
        "/seller/earn/",
        {
            "check_amount": "100000",
            "phone": "+998900000001",
            "idempotency_key": "web-key-1",
        },
    )

    assert response.status_code == 302
    assert get_balance(customer) == Decimal("10000.00")


@pytest.mark.django_db
def test_earn_success_message_is_localized(
    client, make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    make_customer(tenant, phone="+998900000001")
    client.login(username=seller.user.username, password="pass1234")
    client.cookies["seller_lang"] = "en"

    response = client.post(
        "/seller/earn/",
        {"check_amount": "100000", "phone": "+998900000001", "idempotency_key": "web-key-1"},
        follow=True,
    )

    assert response.status_code == 200
    assert b"points added. New balance" in response.content


@pytest.mark.django_db
def test_double_submitting_the_same_earn_form_only_posts_once(
    client, make_tenant, make_branch, make_seller, make_customer
):
    """IMPLEMENTATION_PLAN Phase 4 done-criterion: disputes impossible via
    double-submit. The hidden idempotency_key is generated once when the
    page renders and stays fixed across a double-click / resubmit of that
    same rendered form."""
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant, phone="+998900000001")
    client.login(username=seller.user.username, password="pass1234")

    payload = {
        "check_amount": "100000",
        "phone": "+998900000001",
        "idempotency_key": "same-token-from-one-page-render",
    }
    client.post("/seller/earn/", payload)
    client.post("/seller/earn/", payload)

    assert (
        Transaction.objects.all_tenants().filter(tenant=tenant, customer=customer).count() == 1
    )
    assert get_balance(customer) == Decimal("10000.00")


@pytest.mark.django_db
def test_redeem_end_to_end_with_a_valid_otp(
    client, make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    customer = make_customer(tenant, phone="+998900000001")
    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("1000000"),
        idempotency_key="seed",
    )
    OTP.objects.all_tenants().create(
        tenant=tenant, customer=customer, code="123456", amount_requested=Decimal("40000")
    )
    client.login(username=seller.user.username, password="pass1234")

    response = client.post(
        "/seller/redeem/",
        {
            "check_amount": "100000",
            "otp_code": "123456",
            "idempotency_key": "web-redeem-1",
        },
    )

    assert response.status_code == 302
    otp = OTP.objects.all_tenants().get(tenant=tenant, code="123456")
    assert otp.used is True


@pytest.mark.django_db
def test_earn_over_the_daily_transaction_limit_shows_an_error_instead_of_crashing(
    client, make_tenant, make_branch, make_seller, make_customer
):
    """Previously post_earn_by_phone's DailyTransactionLimitExceededError
    (and MaxCheckAmountExceededError) went uncaught here, so a seller
    hitting their daily cap got Django's raw debug 500 page instead of the
    same friendly redirect+message every other seller-web error uses."""
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    seller.daily_txn_limit = 1
    seller.save(update_fields=["daily_txn_limit"])
    customer = make_customer(tenant, phone="+998900000001")
    client.login(username=seller.user.username, password="pass1234")

    client.post(
        "/seller/earn/",
        {"check_amount": "100000", "phone": "+998900000001", "idempotency_key": "web-key-1"},
    )
    response = client.post(
        "/seller/earn/",
        {"check_amount": "100000", "phone": "+998900000001", "idempotency_key": "web-key-2"},
        follow=True,
    )

    assert response.status_code == 200
    assert "Kunlik tranzaksiya limiti".encode() in response.content
    assert (
        Transaction.objects.all_tenants().filter(tenant=tenant, customer=customer).count() == 1
    )


@pytest.mark.django_db
def test_earn_over_the_max_check_amount_shows_an_error_instead_of_crashing(
    client, make_tenant, make_branch, make_seller
):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    client.login(username=seller.user.username, password="pass1234")

    response = client.post(
        "/seller/earn/",
        {"check_amount": "5000000", "phone": "+998900000099", "idempotency_key": "web-key-1"},
        follow=True,
    )

    assert response.status_code == 200
    assert "maksimal".encode() in response.content
    assert Transaction.objects.all_tenants().filter(tenant=tenant).count() == 0


@pytest.mark.django_db
def test_redeem_over_the_daily_transaction_limit_shows_an_error_instead_of_crashing(
    client, make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t", rate=Decimal("10.00"))
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    seller.daily_txn_limit = 1
    seller.save(update_fields=["daily_txn_limit"])
    customer = make_customer(tenant, phone="+998900000001")
    post_earn_transaction(
        tenant=tenant,
        branch=branch,
        seller=seller,
        customer=customer,
        check_amount=Decimal("1000000"),
        idempotency_key="seed",
    )
    OTP.objects.all_tenants().create(
        tenant=tenant, customer=customer, code="123456", amount_requested=Decimal("40000")
    )
    client.login(username=seller.user.username, password="pass1234")

    response = client.post(
        "/seller/redeem/",
        {"check_amount": "100000", "otp_code": "123456", "idempotency_key": "web-redeem-1"},
        follow=True,
    )

    assert response.status_code == 200
    assert "Kunlik tranzaksiya limiti".encode() in response.content
    otp = OTP.objects.all_tenants().get(tenant=tenant, code="123456")
    assert otp.used is False


@pytest.mark.django_db
def test_redeem_with_invalid_otp_shows_an_error_and_posts_nothing(
    client, make_tenant, make_branch, make_seller, make_customer
):
    tenant = make_tenant("t")
    branch = make_branch(tenant)
    seller = make_seller(tenant, branch)
    make_customer(tenant)
    client.login(username=seller.user.username, password="pass1234")

    response = client.post(
        "/seller/redeem/",
        {
            "check_amount": "100000",
            "otp_code": "000000",
            "idempotency_key": "web-redeem-1",
        },
        follow=True,
    )

    assert response.status_code == 200
    assert Transaction.objects.all_tenants().filter(tenant=tenant).count() == 0
