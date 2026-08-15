import uuid
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from apps.accounts.models import UserProfile
from apps.accounts.ratelimit import RateLimitExceededError
from apps.customers.models import PendingCashback
from apps.ledger.models import Transaction
from apps.ledger.services import (
    DailyRedemptionLimitExceededError,
    DailyTransactionLimitExceededError,
    InsufficientBalanceError,
    InvalidOTPError,
    MaxCheckAmountExceededError,
    get_balance,
    post_earn_by_phone,
    redeem_via_otp,
)
from apps.seller_web.forms import EarnForm, RedeemForm
from apps.seller_web.i18n import LANGUAGE_COOKIE, LANGUAGES, get_language, strings_for, t

# Aligned with the session cookie's own lifetime expectations — long enough
# that picking a language once sticks around, short enough to naturally
# reset rather than accumulate forever.
LANGUAGE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365


def set_language(request):
    """POSTed by the UZ/EN/RU switcher on the login/forbidden pages. No auth
    required — the login page itself needs this before a seller has signed
    in, so the cookie is always set. If the poster already has a profile
    (e.g. the forbidden page, reached post-login by a non-seller role),
    also persist it to UserProfile.language so it stays the same source of
    truth the React panel's profile drawer writes to. Redirects back to
    wherever the form was on."""
    language = request.POST.get("language")
    next_url = request.POST.get("next") or "/"
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = "/"
    response = HttpResponseRedirect(next_url)
    if language in LANGUAGES:
        response.set_cookie(LANGUAGE_COOKIE, language, max_age=LANGUAGE_COOKIE_MAX_AGE)
        profile = getattr(request.user, "profile", None)
        if profile is not None and profile.language != language:
            profile.language = language
            profile.save(update_fields=["language"])
    return response


def seller_required(view_func):
    """Only Seller-role users with a linked Seller row may use this page —
    CLAUDE.md §3: sellers only create earn transactions and confirm
    redemptions, nothing else, and this page is exclusively theirs."""

    @wraps(view_func)
    @login_required(login_url="accounts:login")
    def wrapper(request, *args, **kwargs):
        profile = getattr(request.user, "profile", None)
        seller = getattr(request.user, "seller_profile", None)
        if profile is None or profile.role != UserProfile.Role.SELLER or seller is None:
            language = get_language(request)
            return render(
                request,
                "seller_web/forbidden.html",
                {"s": strings_for(language), "language": language, "languages": LANGUAGES},
                status=403,
            )
        request.seller = seller
        return view_func(request, *args, **kwargs)

    return wrapper


@seller_required
def register(request):
    language = get_language(request)
    context = {
        "earn_form": EarnForm(initial={"idempotency_key": uuid.uuid4().hex}, language=language),
        "redeem_form": RedeemForm(initial={"idempotency_key": uuid.uuid4().hex}, language=language),
        "seller": request.seller,
        "has_tenant_logo": bool(request.seller.tenant.logo),
        "s": strings_for(language),
        "language": language,
        "languages": LANGUAGES,
    }
    return render(request, "seller_web/register.html", context)


@seller_required
def earn(request):
    if request.method != "POST":
        return redirect("seller_web:register")

    language = get_language(request)
    form = EarnForm(request.POST, language=language)
    if not form.is_valid():
        messages.error(request, t(language, "earn_form_invalid"))
        return redirect("seller_web:register")

    seller = request.seller
    try:
        result = post_earn_by_phone(
            tenant=seller.tenant,
            branch=seller.branch,
            seller=seller,
            phone=form.cleaned_data["phone"],
            check_amount=form.cleaned_data["check_amount"],
            no_cashback=form.cleaned_data["no_cashback"],
            idempotency_key=form.cleaned_data["idempotency_key"],
        )
    except (MaxCheckAmountExceededError, DailyTransactionLimitExceededError) as exc:
        messages.error(request, str(exc))
        return redirect("seller_web:register")

    if isinstance(result, Transaction):
        messages.success(
            request,
            t(
                language,
                "earn_success_earned",
                earned=result.cashback_earned,
                balance=get_balance(result.customer),
            ),
        )
    elif isinstance(result, PendingCashback):
        messages.success(request, t(language, "earn_success_pending", amount=result.amount))
    else:
        messages.success(request, t(language, "earn_success_no_cashback"))

    return redirect("seller_web:register")


@seller_required
def redeem(request):
    if request.method != "POST":
        return redirect("seller_web:register")

    language = get_language(request)
    form = RedeemForm(request.POST, language=language)
    if not form.is_valid():
        messages.error(request, t(language, "redeem_form_invalid"))
        return redirect("seller_web:register")

    seller = request.seller
    try:
        txn = redeem_via_otp(
            tenant=seller.tenant,
            branch=seller.branch,
            seller=seller,
            otp_code=form.cleaned_data["otp_code"],
            check_amount=form.cleaned_data["check_amount"],
            no_cashback=form.cleaned_data["no_cashback"],
            idempotency_key=form.cleaned_data["idempotency_key"],
        )
    except (
        InvalidOTPError,
        InsufficientBalanceError,
        MaxCheckAmountExceededError,
        DailyTransactionLimitExceededError,
        DailyRedemptionLimitExceededError,
        RateLimitExceededError,
    ) as exc:
        messages.error(request, str(exc))
        return redirect("seller_web:register")

    messages.success(
        request,
        t(
            language,
            "redeem_success",
            spent=txn.cashback_spent,
            earned=txn.cashback_earned,
            balance=get_balance(txn.customer),
        ),
    )
    return redirect("seller_web:register")


@seller_required
def tenant_logo(request):
    """Streams the seller's own tenant's logo — same self-scoped-only
    convention as avatar() above and apps.accounts.api_views.
    MeTenantLogoView (the React-panel equivalent for tenant_admin/
    branch_manager). Lets the till page show the pharmacy's own branding
    instead of the generic product logo (CLAUDE.md-adjacent — every screen
    a tenant's own people see should read as "their" pharmacy)."""
    tenant = request.seller.tenant
    if not tenant.logo:
        raise Http404
    return FileResponse(tenant.logo.open("rb"), content_type="application/octet-stream")
