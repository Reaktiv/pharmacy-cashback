from decimal import Decimal

from django import forms

from apps.customers.models import phone_validator


class EarnForm(forms.Form):
    check_amount = forms.DecimalField(
        min_value=Decimal("0.01"), max_digits=12, decimal_places=2, label="Check amount"
    )
    phone = forms.CharField(
        max_length=20, validators=[phone_validator], label="Customer phone (+998...)"
    )
    no_cashback = forms.BooleanField(
        required=False, label="No cashback (prescription only)"
    )
    idempotency_key = forms.CharField(widget=forms.HiddenInput)


class RedeemForm(forms.Form):
    check_amount = forms.DecimalField(
        min_value=Decimal("0.01"), max_digits=12, decimal_places=2, label="Check amount"
    )
    otp_code = forms.CharField(min_length=6, max_length=6, label="OTP code")
    no_cashback = forms.BooleanField(
        required=False, label="No cashback (prescription only)"
    )
    idempotency_key = forms.CharField(widget=forms.HiddenInput)
