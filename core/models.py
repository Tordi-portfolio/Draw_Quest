from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models, transaction
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

MONEY = {"max_digits": 12, "decimal_places": 2}


class Profile(models.Model):
    """Per-user dashboard data. `balance` is the points balance, valued in $."""

    class Role(models.TextChoices):
        MEMBER = "member", "Member"
        CREATOR = "creator", "Creator"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    avatar = models.ImageField(upload_to="avatars/", blank=True)
    bio = models.CharField(max_length=160, blank=True)
    balance = models.DecimalField(default=Decimal("0.00"), **MONEY)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} ({self.get_role_display()})"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)


class TaskQuerySet(models.QuerySet):
    def open(self):
        """Active tasks whose deadline (if any) hasn't passed."""
        return self.filter(is_active=True).filter(
            Q(deadline__isnull=True) | Q(deadline__gt=timezone.now())
        )


class Task(models.Model):
    class Category(models.TextChoices):
        SKETCH = "sketch", "Sketch"
        DIGITAL = "digital", "Digital art"
        CHARACTER = "character", "Character"
        LANDSCAPE = "landscape", "Landscape"
        ABSTRACT = "abstract", "Abstract"
        OTHER = "other", "Other"

    title = models.CharField(max_length=120)
    description = models.TextField(help_text="What should the artist draw? Be specific.")
    reference_image = models.ImageField(upload_to="tasks/", blank=True)
    reward = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Amount in $ credited to the user's dashboard when approved.",
    )
    category = models.CharField(
        max_length=12, choices=Category.choices, default=Category.OTHER
    )
    deadline = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_tasks",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TaskQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def is_open(self):
        if not self.is_active:
            return False
        return self.deadline is None or self.deadline > timezone.now()


class Submission(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="submissions")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="submissions"
    )
    image = models.ImageField(upload_to="submissions/%Y/%m/")
    caption = models.CharField(max_length=200, blank=True)
    # Snapshot of the task price when submitted, so later price edits don't change it.
    reward = models.DecimalField(max_digits=8, decimal_places=2)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    admin_feedback = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviews",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} → {self.task} ({self.get_status_display()})"

    @transaction.atomic
    def approve(self, reviewer, feedback=""):
        """Mark approved and credit the user's dashboard exactly once."""
        sub = Submission.objects.select_for_update().get(pk=self.pk)
        if sub.status != self.Status.PENDING:
            raise ValueError("This submission has already been reviewed.")
        profile, _ = Profile.objects.select_for_update().get_or_create(user_id=sub.user_id)
        profile.balance += sub.reward
        profile.save(update_fields=["balance"])
        PointTransaction.objects.create(
            user_id=sub.user_id,
            amount=sub.reward,
            kind=PointTransaction.Kind.REWARD,
            note=f"Approved: {sub.task.title}",
            submission=sub,
            created_by=reviewer,
        )
        sub.status = self.Status.APPROVED
        sub.admin_feedback = feedback
        sub.reviewed_by = reviewer
        sub.reviewed_at = timezone.now()
        sub.save()
        self.refresh_from_db()

    @transaction.atomic
    def reject(self, reviewer, feedback=""):
        sub = Submission.objects.select_for_update().get(pk=self.pk)
        if sub.status != self.Status.PENDING:
            raise ValueError("This submission has already been reviewed.")
        sub.status = self.Status.REJECTED
        sub.admin_feedback = feedback
        sub.reviewed_by = reviewer
        sub.reviewed_at = timezone.now()
        sub.save()
        self.refresh_from_db()


class PointTransaction(models.Model):
    """Ledger of every change to a user's balance."""

    class Kind(models.TextChoices):
        REWARD = "reward", "Task reward"
        BONUS = "bonus", "Admin credit"
        ADJUSTMENT = "adjustment", "Admin adjustment"
        WITHDRAWAL = "withdrawal", "Withdrawal"
        REFUND = "refund", "Withdrawal refund"
        DEPOSIT = "deposit", "Deposit"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transactions"
    )
    amount = models.DecimalField(**MONEY)
    kind = models.CharField(max_length=12, choices=Kind.choices)  # longest value: "adjustment"
    note = models.CharField(max_length=200, blank=True)
    submission = models.ForeignKey(
        Submission, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.user} {self.amount:+}"


class Withdrawal(models.Model):
    """A user's request to cash out. The amount is taken off their balance when
    they request it (so it can't be spent twice) and refunded if rejected."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        PAID = "paid", "Paid"
        REJECTED = "rejected", "Rejected"

    class Method(models.TextChoices):
        BANK = "bank", "Bank transfer"
        PAYPAL = "paypal", "PayPal"
        MOBILE = "mobile_money", "Mobile money"
        CRYPTO = "crypto", "Crypto wallet (USDT)"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="withdrawals"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=14, choices=Method.choices, default=Method.BANK)
    account_details = models.TextField(
        help_text="Where to send the money: account name and number, PayPal email, wallet address, etc."
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    payment_reference = models.CharField(max_length=120, blank=True)
    admin_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} ${self.amount} ({self.get_status_display()})"

    @transaction.atomic
    def mark_paid(self, reviewer, reference="", note=""):
        """Admin confirms the money has been sent. Balance was already deducted."""
        w = Withdrawal.objects.select_for_update().get(pk=self.pk)
        if w.status != self.Status.PENDING:
            raise ValueError("This withdrawal has already been reviewed.")
        w.status = self.Status.PAID
        w.payment_reference = reference
        w.admin_note = note
        w.reviewed_by = reviewer
        w.reviewed_at = timezone.now()
        w.save()
        self.refresh_from_db()

    @transaction.atomic
    def reject(self, reviewer, note=""):
        """Admin declines. The held amount goes back to the user's balance, once."""
        w = Withdrawal.objects.select_for_update().get(pk=self.pk)
        if w.status != self.Status.PENDING:
            raise ValueError("This withdrawal has already been reviewed.")
        profile, _ = Profile.objects.select_for_update().get_or_create(user_id=w.user_id)
        profile.balance += w.amount
        profile.save(update_fields=["balance"])
        PointTransaction.objects.create(
            user_id=w.user_id,
            amount=w.amount,
            kind=PointTransaction.Kind.REFUND,
            note=f"Withdrawal #{w.pk} rejected, funds returned",
            created_by=reviewer,
        )
        w.status = self.Status.REJECTED
        w.admin_note = note
        w.reviewed_by = reviewer
        w.reviewed_at = timezone.now()
        w.save()
        self.refresh_from_db()


class DepositSettings(models.Model):
    """Single-row settings: the USDT (BSC) wallet shown on the deposit page.
    Edit it in the Django admin at /admin/ (superusers only)."""

    wallet_address = models.CharField(
        "USDT wallet address (BSC)",
        max_length=42,
        blank=True,
        validators=[
            RegexValidator(
                r"^0x[a-fA-F0-9]{40}$",
                "Enter a valid BSC address: 0x followed by 40 letters/numbers (42 characters in total).",
            )
        ],
        help_text="Shown to users on the deposit page. Double-check it: money sent here goes to this wallet.",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Deposit wallet"
        verbose_name_plural = "Deposit wallet"

    def __str__(self):
        return "USDT deposit wallet (BSC)"

    def save(self, *args, **kwargs):
        self.pk = 1  # always exactly one row
        self.wallet_address = self.wallet_address.strip()
        super().save(*args, **kwargs)


class DepositRequest(models.Model):
    """A user says "I sent USDT on BSC, here's the transaction ID". An admin checks
    the transaction on the blockchain and credits the verified amount."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending verification"
        CREDITED = "credited", "Credited"
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="deposits"
    )
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, help_text="Amount of USDT you sent."
    )
    # Lower-cased 0x + 64 hex characters. Unique so one transaction can't be claimed twice.
    tx_hash = models.CharField(max_length=66, unique=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    credited_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    admin_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} claims ${self.amount} ({self.get_status_display()})"

    @transaction.atomic
    def approve(self, reviewer, credited_amount, note=""):
        """Credit the verified amount to the user's balance, exactly once."""
        d = DepositRequest.objects.select_for_update().get(pk=self.pk)
        if d.status != self.Status.PENDING:
            raise ValueError("This deposit has already been reviewed.")
        profile, _ = Profile.objects.select_for_update().get_or_create(user_id=d.user_id)
        profile.balance += credited_amount
        profile.save(update_fields=["balance"])
        PointTransaction.objects.create(
            user_id=d.user_id,
            amount=credited_amount,
            kind=PointTransaction.Kind.DEPOSIT,
            note=f"USDT deposit #{d.pk} (BSC)",
            created_by=reviewer,
        )
        d.status = self.Status.CREDITED
        d.credited_amount = credited_amount
        d.admin_note = note
        d.reviewed_by = reviewer
        d.reviewed_at = timezone.now()
        d.save()
        self.refresh_from_db()

    @transaction.atomic
    def reject(self, reviewer, note=""):
        d = DepositRequest.objects.select_for_update().get(pk=self.pk)
        if d.status != self.Status.PENDING:
            raise ValueError("This deposit has already been reviewed.")
        d.status = self.Status.REJECTED
        d.admin_note = note
        d.reviewed_by = reviewer
        d.reviewed_at = timezone.now()
        d.save()
        self.refresh_from_db()


class Announcement(models.Model):
    """Posts the admin publishes onto every user's dashboard."""

    title = models.CharField(max_length=120)
    body = models.TextField(blank=True)
    image = models.ImageField(upload_to="announcements/", blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
