import uuid
from functools import wraps

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from apps.accounts.models import UserProfile
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
from apps.seller_web.forms import EarnForm, ProfileForm, RedeemForm, SellerPasswordChangeForm
from apps.seller_web.i18n import LANGUAGE_COOKIE, LANGUAGES, get_language, strings_for, t

# Aligned with the session cookie's own lifetime expectations — long enough
# that picking a language once sticks around, short enough to naturally
# reset rather than accumulate forever.
LANGUAGE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365


def set_language(request):
    """POSTed by the UZ/EN/RU switcher on the login/register/forbidden
    pages. No auth required — the login page itself needs this before a
    seller has signed in. Redirects back to wherever the form was on."""
    language = request.POST.get("language")
    next_url = request.POST.get("next") or "/"
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = "/"
    response = HttpResponseRedirect(next_url)
    if language in LANGUAGES:
        response.set_cookie(LANGUAGE_COOKIE, language, max_age=LANGUAGE_COOKIE_MAX_AGE)
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
        "has_avatar": bool(request.user.profile.avatar),
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
            t(language, "earn_success_earned", earned=result.cashback_earned, balance=get_balance(result.customer)),
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
def profile(request):
    """Self-service "who am I" page for the seller-web till (README: sellers
    use this session-based app, not the JWT React panel, so they get their
    own small profile page mirroring apps.accounts.api_views.MeView). Name/
    phone write through to the Seller row — the copy every report and the
    Sellers list actually read (apps.accounts.signals.sync_profile_with_seller
    mirrors it back onto UserProfile automatically). Avatar has no Seller
    column, so it always lives directly on UserProfile."""
    language = get_language(request)
    seller = request.seller
    user_profile = request.user.profile

    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, language=language)
        if form.is_valid():
            seller.full_name = form.cleaned_data["full_name"]
            seller.phone = form.cleaned_data["phone"]
            seller.save(update_fields=["full_name", "phone"])

            if form.cleaned_data["remove_avatar"] and user_profile.avatar:
                user_profile.avatar.delete(save=False)
                user_profile.avatar = None
                user_profile.save(update_fields=["avatar"])
            elif form.cleaned_data["avatar"] is not None:
                user_profile.avatar = form.cleaned_data["avatar"]
                user_profile.save(update_fields=["avatar"])

            messages.success(request, t(language, "profile_saved"))
            # Same "back to the main page" behavior as the React admin
            # panel's profile drawer after a successful save.
            return redirect("seller_web:register")
        messages.error(request, t(language, "profile_form_invalid"))
    else:
        form = ProfileForm(
            initial={"full_name": seller.full_name, "phone": seller.phone},
            language=language,
        )

    context = {
        "form": form,
        "password_form": SellerPasswordChangeForm(request.user, language=language),
        "seller": seller,
        "has_avatar": bool(user_profile.avatar),
        "has_tenant_logo": bool(seller.tenant.logo),
        "s": strings_for(language),
        "language": language,
        "languages": LANGUAGES,
    }
    return render(request, "seller_web/profile.html", context)


@seller_required
def change_password(request):
    """Old/new/confirm password flow — login itself stays admin-managed,
    only the password behind it is self-service (matches
    apps.accounts.api_views.ChangePasswordView for the React panel roles)."""
    language = get_language(request)
    if request.method == "POST":
        form = SellerPasswordChangeForm(request.user, request.POST, language=language)
        if form.is_valid():
            user = form.save()
            # Django's session auth hash is derived from the password —
            # without this, changing your own password logs you out
            # mid-session.
            update_session_auth_hash(request, user)
            messages.success(request, t(language, "password_changed"))
        else:
            messages.error(request, t(language, "password_change_error"))
    return redirect("seller_web:profile")


@seller_required
def avatar(request):
    """Streams the logged-in seller's own avatar — scoped to request.user
    only (never an arbitrary id), same convention as
    apps.accounts.api_views.MeAvatarView (CLAUDE.md §4: no tenant/role check
    to get wrong when the query can only ever be "my own file")."""
    user_profile = request.user.profile
    if not user_profile.avatar:
        raise Http404
    return FileResponse(user_profile.avatar.open("rb"), content_type="application/octet-stream")


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
