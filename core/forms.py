import re
from decimal import Decimal

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import Announcement, DepositRequest, Profile, Submission, Task, Withdrawal

User = get_user_model()
DT_FORMAT = "%Y-%m-%dT%H:%M"


class StyledMixin:
    """Gives every widget the shared `.field` class used by the UI."""

    def _style(self):
        for name, f in self.fields.items():
            w = f.widget
            if isinstance(w, (forms.CheckboxInput, forms.FileInput)):
                continue
            w.attrs["class"] = (w.attrs.get("class", "") + " field").strip()


def validate_image_size(f):
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    if f and f.size > limit:
        raise forms.ValidationError(f"Image is too large. Max size is {settings.MAX_UPLOAD_MB} MB.")
    return f


class StyledAuthForm(StyledMixin, AuthenticationForm):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._style()
        self.fields["username"].widget.attrs.update(
            {"placeholder": "Username", "autofocus": True}
        )
        self.fields["password"].widget.attrs.update({"placeholder": "Password"})


class SignUpForm(StyledMixin, UserCreationForm):
    email = forms.EmailField(required=True)
    role = forms.ChoiceField(
        choices=Profile.Role.choices,
        initial=Profile.Role.MEMBER,
        widget=forms.RadioSelect,
        label="I want to join as",
    )

    class Meta:
        model = User
        fields = ("username", "email")

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._style()
        self.fields["role"].widget.attrs.pop("class", None)
        for name, ph in {
            "username": "Pick a username",
            "email": "you@example.com",
            "password1": "Create a password",
            "password2": "Repeat password",
        }.items():
            self.fields[name].widget.attrs["placeholder"] = ph

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.role = self.cleaned_data["role"]
            profile.save(update_fields=["role"])
        return user


class SubmissionForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Submission
        fields = ("image", "caption")
        widgets = {
            "image": forms.FileInput(attrs={"accept": "image/*"}),
            "caption": forms.TextInput(
                attrs={"placeholder": "Add a note for the reviewer (optional)"}
            ),
        }

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._style()

    def clean_image(self):
        return validate_image_size(self.cleaned_data.get("image"))


class ProfileForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Profile
        fields = ("avatar", "bio", "role")
        widgets = {"avatar": forms.FileInput(attrs={"accept": "image/*"})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._style()

    def clean_avatar(self):
        return validate_image_size(self.cleaned_data.get("avatar"))


class TaskForm(StyledMixin, forms.ModelForm):
    deadline = forms.DateTimeField(
        required=False,
        input_formats=[DT_FORMAT],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format=DT_FORMAT),
        help_text="Optional. Leave empty for no deadline.",
    )

    class Meta:
        model = Task
        fields = (
            "title",
            "description",
            "reference_image",
            "reward",
            "category",
            "deadline",
            "is_active",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
            "reference_image": forms.FileInput(attrs={"accept": "image/*"}),
            "reward": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
        }
        labels = {"reward": "Reward ($)", "is_active": "Visible to users"}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._style()

    def clean_reference_image(self):
        return validate_image_size(self.cleaned_data.get("reference_image"))


class ReviewForm(StyledMixin, forms.Form):
    feedback = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Feedback for the artist (required when rejecting)"}
        ),
    )

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._style()


class CreditForm(StyledMixin, forms.Form):
    amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "placeholder": "e.g. 5.00 or -2.50"}),
        help_text="Use a negative amount to deduct.",
    )
    note = forms.CharField(
        max_length=200, widget=forms.TextInput(attrs={"placeholder": "Reason shown to the user"})
    )

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._style()

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount == Decimal("0"):
            raise forms.ValidationError("Amount can't be zero.")
        return amount


class WithdrawalForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Withdrawal
        fields = ("amount", "method", "account_details")
        widgets = {
            "amount": forms.NumberInput(attrs={"step": "0.01"}),
            "account_details": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Bank name, account name and number, or PayPal email, or wallet address and network",
                }
            ),
        }
        labels = {"amount": "Amount ($)", "account_details": "Payout details"}

    def __init__(self, *a, profile=None, **kw):
        super().__init__(*a, **kw)
        self.profile = profile
        self._style()
        self.fields["amount"].widget.attrs["min"] = str(settings.WITHDRAWAL_MIN)
        self.fields["amount"].widget.attrs["placeholder"] = f"Min. {settings.WITHDRAWAL_MIN}"

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount < settings.WITHDRAWAL_MIN:
            raise forms.ValidationError(
                f"The minimum withdrawal is ${settings.WITHDRAWAL_MIN:,.2f}."
            )
        if self.profile is not None and amount > self.profile.balance:
            raise forms.ValidationError("You can't withdraw more than your balance.")
        return amount

    def clean_account_details(self):
        details = self.cleaned_data["account_details"].strip()
        if len(details) < 8:
            raise forms.ValidationError("Please give full payout details so we can pay you.")
        return details


class WithdrawalReviewForm(StyledMixin, forms.Form):
    payment_reference = forms.CharField(
        required=False,
        max_length=120,
        label="Payment reference",
        widget=forms.TextInput(attrs={"placeholder": "Transfer ID / transaction hash (when marking paid)"}),
    )
    note = forms.CharField(
        required=False,
        label="Note to user",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Required when rejecting"}),
    )

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._style()


class DepositForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = DepositRequest
        fields = ("amount", "tx_hash")
        widgets = {
            "amount": forms.NumberInput(attrs={"step": "0.01", "min": "0.01", "placeholder": "e.g. 50.00"}),
            "tx_hash": forms.TextInput(attrs={"placeholder": "0x… (66 characters)", "spellcheck": "false", "autocomplete": "off"}),
        }
        labels = {"amount": "Amount sent (USDT)", "tx_hash": "Transaction ID (TxID / hash)"}
        error_messages = {"tx_hash": {"unique": "This transaction has already been submitted."}}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._style()

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Enter the amount you sent.")
        return amount

    def clean_tx_hash(self):
        value = self.cleaned_data["tx_hash"].strip().lower()
        if not re.fullmatch(r"0x[0-9a-f]{64}", value):
            raise forms.ValidationError(
                "That doesn't look like a BSC transaction hash (0x followed by 64 letters/numbers)."
            )
        return value


class DepositReviewForm(StyledMixin, forms.Form):
    credited_amount = forms.DecimalField(
        required=False,
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Amount to credit ($)",
        help_text="Credit what you verified arrived on-chain, not just what the user claimed.",
        widget=forms.NumberInput(attrs={"step": "0.01"}),
    )
    note = forms.CharField(
        required=False,
        label="Note to user",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Required when rejecting"}),
    )

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._style()


class AnnouncementForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ("title", "body", "image", "is_active")
        widgets = {
            "body": forms.Textarea(attrs={"rows": 3}),
            "image": forms.FileInput(attrs={"accept": "image/*"}),
        }
        labels = {"is_active": "Show on user dashboards"}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._style()

    def clean_image(self):
        return validate_image_size(self.cleaned_data.get("image"))
