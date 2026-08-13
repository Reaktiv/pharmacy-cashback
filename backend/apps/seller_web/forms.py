from decimal import Decimal

from django import forms
from django.contrib.auth.forms import PasswordChangeForm

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


# Deliberately smaller than the broadcast composer's 10MB image cap
# (apps.broadcasts.serializers.MAX_IMAGE_BYTES) — a self-service avatar,
# not a promotional image.
AVATAR_MAX_BYTES = 5 * 1024 * 1024


class ProfileForm(forms.Form):
    """Self-service name/phone/avatar for the seller-web "who am I" page —
    full_name/phone are written to the Seller row (the copy every report
    actually reads), avatar to UserProfile (see apps.seller_web.views.profile).
    """

    full_name = forms.CharField(max_length=255)
    phone = forms.CharField(max_length=20, validators=[phone_validator])
    avatar = forms.FileField(required=False)
    remove_avatar = forms.BooleanField(required=False)

    def __init__(self, *args, language: str = DEFAULT_LANGUAGE, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["full_name"].label = t(language, "profile_full_name_label")
        self.fields["phone"].label = t(language, "profile_phone_label")
        self._language = language

    def clean_avatar(self):
        uploaded_file = self.cleaned_data.get("avatar")
        if uploaded_file is None:
            return uploaded_file
        content_type = uploaded_file.content_type or ""
        if not content_type.startswith("image/"):
            raise forms.ValidationError(t(self._language, "profile_avatar_invalid_type"))
        if uploaded_file.size > AVATAR_MAX_BYTES:
            raise forms.ValidationError(
                t(
                    self._language,
                    "profile_avatar_too_large",
                    size=AVATAR_MAX_BYTES // (1024 * 1024),
                )
            )
        return uploaded_file


class SellerPasswordChangeForm(PasswordChangeForm):
    """Django's built-in old/new/confirm password flow, relabeled with our
    own i18n strings. Login itself is never editable from here — only the
    password behind it."""

    def __init__(self, *args, language: str = DEFAULT_LANGUAGE, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = t(language, "current_password_label")
        self.fields["new_password1"].label = t(language, "new_password_label")
        self.fields["new_password2"].label = t(language, "confirm_new_password_label")
