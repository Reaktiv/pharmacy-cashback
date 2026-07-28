import uuid
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.accounts.models import UserProfile
from apps.customers.models import PendingCashback
from apps.ledger.models import Transaction
from apps.ledger.services import (
    InsufficientBalanceError,
    InvalidOTPError,
    get_balance,
    post_earn_by_phone,
    redeem_via_otp,
)
from apps.seller_web.forms import EarnForm, RedeemForm


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
            return render(request, "seller_web/forbidden.html", status=403)
        request.seller = seller
        return view_func(request, *args, **kwargs)

    return wrapper


@seller_required
def register(request):
    context = {
        "earn_form": EarnForm(initial={"idempotency_key": uuid.uuid4().hex}),
        "redeem_form": RedeemForm(initial={"idempotency_key": uuid.uuid4().hex}),
        "seller": request.seller,
    }
    return render(request, "seller_web/register.html", context)


@seller_required
def earn(request):
    if request.method != "POST":
        return redirect("seller_web:register")

    form = EarnForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please check the amount and phone number.")
        return redirect("seller_web:register")

    seller = request.seller
    result = post_earn_by_phone(
        tenant=seller.tenant,
        branch=seller.branch,
        seller=seller,
        phone=form.cleaned_data["phone"],
        check_amount=form.cleaned_data["check_amount"],
        no_cashback=form.cleaned_data["no_cashback"],
        idempotency_key=form.cleaned_data["idempotency_key"],
    )

    if isinstance(result, Transaction):
        messages.success(
            request,
            f"Earned {result.cashback_earned} points. "
            f"New balance: {get_balance(result.customer)}.",
        )
    elif isinstance(result, PendingCashback):
        messages.success(
            request,
            f"Customer not registered yet — {result.amount} points will be credited "
            "once they join the bot.",
        )
    else:
        messages.success(request, "Sale recorded. No cashback earned.")

    return redirect("seller_web:register")


@seller_required
def redeem(request):
    if request.method != "POST":
        return redirect("seller_web:register")

    form = RedeemForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please check the amount and OTP code.")
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
    except InvalidOTPError as exc:
        messages.error(request, str(exc))
        return redirect("seller_web:register")
    except InsufficientBalanceError as exc:
        messages.error(request, str(exc))
        return redirect("seller_web:register")

    messages.success(
        request,
        f"Redeemed {txn.cashback_spent} points, earned {txn.cashback_earned} more. "
        f"New balance: {get_balance(txn.customer)}.",
    )
    return redirect("seller_web:register")
