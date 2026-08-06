from decimal import Decimal

from django import forms

from apps.customers.models import phone_validator
from apps.seller_web.i18n import DEFAULT_LANGUAGE, t


class EarnForm(forms.Form):
    check_amount = forms.DecimalField(min_value=Decimal("0.01"), max_digits=12, decimal_places=2)
    phone = forms.CharField(max_length=20, validators=[phone_validator])
    no_cashback = forms.BooleanField(required=False)
    idempotency_key = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, *args, language: str = DEFAULT_LANGUAGE, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["check_amount"].label = t(language, "check_amount_label")
        self.fields["phone"].label = t(language, "customer_phone_label")
        self.fields["no_cashback"].label = t(language, "no_cashback_label")


class RedeemForm(forms.Form):
    check_amount = forms.DecimalField(min_value=Decimal("0.01"), max_digits=12, decimal_places=2)
    otp_code = forms.CharField(min_length=6, max_length=6)
    no_cashback = forms.BooleanField(required=False)
    idempotency_key = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, *args, language: str = DEFAULT_LANGUAGE, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["check_amount"].label = t(language, "check_amount_label")
        self.fields["otp_code"].label = t(language, "otp_code_label")
        self.fields["no_cashback"].label = t(language, "no_cashback_label")
