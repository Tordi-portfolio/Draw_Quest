import re
from decimal import Decimal
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import (
    AnnouncementForm,
    CreditForm,
    DepositForm,
    DepositReviewForm,
    ProfileForm,
    ReviewForm,
    SignUpForm,
    SubmissionForm,
    TaskForm,
    WithdrawalForm,
    WithdrawalReviewForm,
)
from .models import (
    Announcement,
    DepositRequest,
    DepositSettings,
    PointTransaction,
    Profile,
    Submission,
    Task,
    Withdrawal,
)

User = get_user_model()
ZERO = Decimal("0.00")
BSC_ADDRESS_RE = re.compile(r"0x[a-fA-F0-9]{40}")


def configured_deposit_address():
    """The receiving wallet: the one saved in the Django admin (/admin/ → Deposit
    wallet), falling back to the DRAWQUEST_USDT_WALLET env var / settings value.
    Returns "" if missing or malformed (deposits then stay switched off rather than
    showing users a wrong address)."""
    row = DepositSettings.objects.first()
    addr = (row.wallet_address if row and row.wallet_address else settings.DEPOSIT_WALLET_ADDRESS) or ""
    addr = addr.strip()
    return addr if BSC_ADDRESS_RE.fullmatch(addr) else ""


# ---------------------------------------------------------------- helpers
def staff_required(view):
    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def get_profile(user):
    return Profile.objects.get_or_create(user=user)[0]


def paginate(request, queryset, per_page=12):
    return Paginator(queryset, per_page).get_page(request.GET.get("page"))


def query_without_page(request):
    q = request.GET.copy()
    q.pop("page", None)
    return q.urlencode()


def permission_denied(request, exception=None):
    return render(request, "errors/403.html", status=403)


def not_found(request, exception=None):
    return render(request, "errors/404.html", status=404)


# ------------------------------------------------------------- public pages
def home(request):
    stats = {
        "paid": PointTransaction.objects.filter(kind=PointTransaction.Kind.REWARD).aggregate(
            s=Sum("amount")
        )["s"]
        or ZERO,
        "artists": User.objects.filter(is_staff=False).count(),
        "approved": Submission.objects.filter(status=Submission.Status.APPROVED).count(),
        "open_tasks": Task.objects.open().count(),
    }
    featured = Task.objects.open()[:6]
    return render(request, "home.html", {"stats": stats, "featured": featured})


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Welcome to DrawQuest! Pick a task and start drawing.")
        return redirect("tasks")
    return render(request, "registration/signup.html", {"form": form})


# --------------------------------------------------------------- user area
@login_required
def task_list(request):
    qs = Task.objects.open()
    category = request.GET.get("category", "")
    q = request.GET.get("q", "").strip()
    if category:
        qs = qs.filter(category=category)
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
    tasks = list(qs)
    mine = {}
    for s in Submission.objects.filter(user=request.user, task__in=tasks).order_by("created_at"):
        mine[s.task_id] = s.status  # latest submission wins
    for t in tasks:
        t.my_status = mine.get(t.pk)
    return render(
        request,
        "tasks/list.html",
        {
            "tasks": tasks,
            "categories": Task.Category.choices,
            "active_category": category,
            "q": q,
        },
    )


@login_required
def task_detail(request, pk):
    task = get_object_or_404(Task, pk=pk)
    attempts = task.submissions.filter(user=request.user)
    blocked = attempts.filter(
        status__in=[Submission.Status.PENDING, Submission.Status.APPROVED]
    ).exists()
    can_submit = task.is_open and not blocked

    if request.method == "POST":
        if not can_submit:
            messages.error(request, "You can't submit to this task right now.")
            return redirect("task_detail", pk=task.pk)
        form = SubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            sub = form.save(commit=False)
            sub.task = task
            sub.user = request.user
            sub.reward = task.reward
            sub.save()
            messages.success(request, "Submitted! An admin will review your drawing soon.")
            return redirect("my_submissions")
    else:
        form = SubmissionForm()

    return render(
        request,
        "tasks/detail.html",
        {
            "task": task,
            "form": form,
            "attempts": attempts,
            "can_submit": can_submit,
            "blocked": blocked,
        },
    )


@login_required
def dashboard(request):
    profile = get_profile(request.user)
    counts = request.user.submissions.aggregate(
        pending=Count("id", filter=Q(status=Submission.Status.PENDING)),
        approved=Count("id", filter=Q(status=Submission.Status.APPROVED)),
        rejected=Count("id", filter=Q(status=Submission.Status.REJECTED)),
    )
    # Lifetime earnings = rewards + admin credits only (refunds aren't new earnings).
    earned = (
        PointTransaction.objects.filter(
            user=request.user,
            kind__in=[PointTransaction.Kind.REWARD, PointTransaction.Kind.BONUS],
        ).aggregate(s=Sum("amount"))["s"]
        or ZERO
    )
    min_withdrawal = settings.WITHDRAWAL_MIN
    progress = min(100, int(profile.balance / min_withdrawal * 100))
    return render(
        request,
        "dashboard.html",
        {
            "profile": profile,
            "counts": counts,
            "earned": earned,
            "min_withdrawal": min_withdrawal,
            "withdraw_progress": progress,
            "can_withdraw": profile.balance >= min_withdrawal,
            "pending_withdrawal": request.user.withdrawals.filter(
                status=Withdrawal.Status.PENDING
            ).first(),
            "recent_subs": request.user.submissions.select_related("task")[:6],
            "transactions": request.user.transactions.all()[:8],
            "announcements": Announcement.objects.filter(is_active=True)[:3],
            "suggested": Task.objects.open()[:3],
        },
    )


@login_required
def my_submissions(request):
    status = request.GET.get("status", "")
    qs = request.user.submissions.select_related("task")
    if status in Submission.Status.values:
        qs = qs.filter(status=status)
    return render(
        request,
        "my_submissions.html",
        {
            "page": paginate(request, qs, 9),
            "status": status,
            "statuses": Submission.Status.choices,
            "qs": query_without_page(request),
        },
    )


@login_required
def profile_edit(request):
    profile = get_profile(request.user)
    form = ProfileForm(request.POST or None, request.FILES or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile updated.")
        return redirect("profile")
    return render(request, "profile.html", {"form": form, "profile": profile})


MAX_OPEN_DEPOSIT_CLAIMS = 5


@login_required
def deposit(request):
    address = configured_deposit_address()
    open_claims = request.user.deposits.filter(status=DepositRequest.Status.PENDING).count()
    form = DepositForm(request.POST or None)

    if request.method == "POST":
        if not address:
            messages.error(request, "Deposits are currently unavailable.")
            return redirect("deposit")
        if open_claims >= MAX_OPEN_DEPOSIT_CLAIMS:
            messages.error(
                request,
                "You have several deposits waiting for verification. Please wait for them to be reviewed.",
            )
            return redirect("deposit")
        if form.is_valid():
            claim = form.save(commit=False)
            claim.user = request.user
            claim.save()
            messages.success(
                request,
                "Thanks! We'll verify your transaction on the blockchain and credit your balance.",
            )
            return redirect("deposit")

    return render(
        request,
        "deposit.html",
        {
            "address": address,
            "network": settings.DEPOSIT_NETWORK,
            "network_label": settings.DEPOSIT_NETWORK_LABEL,
            "token": settings.DEPOSIT_TOKEN,
            "form": form,
            "history": request.user.deposits.all()[:15],
        },
    )


@login_required
def withdraw(request):
    profile = get_profile(request.user)
    min_amount = settings.WITHDRAWAL_MIN
    pending = request.user.withdrawals.filter(status=Withdrawal.Status.PENDING).first()
    form = WithdrawalForm(request.POST or None, profile=profile)

    if request.method == "POST":
        if pending:
            messages.error(request, "You already have a withdrawal waiting for review.")
            return redirect("withdraw")
        if form.is_valid():
            amount = form.cleaned_data["amount"]
            with transaction.atomic():
                # Lock the balance row so two requests can't spend the same money.
                locked = Profile.objects.select_for_update().get(pk=profile.pk)
                if amount > locked.balance:
                    form.add_error("amount", "You can't withdraw more than your balance.")
                else:
                    locked.balance -= amount
                    locked.save(update_fields=["balance"])
                    w = form.save(commit=False)
                    w.user = request.user
                    w.save()
                    PointTransaction.objects.create(
                        user=request.user,
                        amount=-amount,
                        kind=PointTransaction.Kind.WITHDRAWAL,
                        note=f"Withdrawal request #{w.pk}",
                        created_by=request.user,
                    )
                    messages.success(
                        request,
                        f"Withdrawal of ${amount} requested. An admin will review it shortly.",
                    )
                    return redirect("withdraw")

    return render(
        request,
        "withdraw.html",
        {
            "form": form,
            "profile": profile,
            "min_amount": min_amount,
            "can_withdraw": profile.balance >= min_amount and not pending,
            "short_by": max(min_amount - profile.balance, ZERO),
            "progress": min(100, int(profile.balance / min_amount * 100)),
            "pending": pending,
            "history": request.user.withdrawals.all()[:20],
        },
    )


# ------------------------------------------------------------- admin panel
@staff_required
def panel_home(request):
    stats = {
        "pending": Submission.objects.filter(status=Submission.Status.PENDING).count(),
        "approved": Submission.objects.filter(status=Submission.Status.APPROVED).count(),
        "tasks": Task.objects.filter(is_active=True).count(),
        "users": User.objects.filter(is_staff=False).count(),
        "paid": PointTransaction.objects.filter(kind=PointTransaction.Kind.REWARD).aggregate(
            s=Sum("amount")
        )["s"]
        or ZERO,
        "withdrawals_pending": Withdrawal.objects.filter(
            status=Withdrawal.Status.PENDING
        ).count(),
        "withdrawn": Withdrawal.objects.filter(status=Withdrawal.Status.PAID).aggregate(
            s=Sum("amount")
        )["s"]
        or ZERO,
    }
    queue = (
        Submission.objects.filter(status=Submission.Status.PENDING)
        .select_related("task", "user")
        .order_by("created_at")[:6]
    )
    return render(request, "panel/home.html", {"stats": stats, "queue": queue})


@staff_required
def panel_submissions(request):
    status = request.GET.get("status", Submission.Status.PENDING)
    q = request.GET.get("q", "").strip()
    qs = Submission.objects.select_related("task", "user")
    if status in Submission.Status.values:
        qs = qs.filter(status=status)
    else:
        status = "all"
    if q:
        qs = qs.filter(Q(user__username__icontains=q) | Q(task__title__icontains=q))
    if status == Submission.Status.PENDING:
        qs = qs.order_by("created_at")  # oldest first = fair queue
    return render(
        request,
        "panel/submissions.html",
        {
            "page": paginate(request, qs, 12),
            "status": status,
            "statuses": Submission.Status.choices,
            "q": q,
            "qs": query_without_page(request),
        },
    )


@staff_required
def panel_review(request, pk):
    sub = get_object_or_404(Submission.objects.select_related("task", "user"), pk=pk)
    form = ReviewForm(request.POST or None, initial={"feedback": sub.admin_feedback})

    if request.method == "POST" and form.is_valid():
        decision = request.POST.get("decision")
        feedback = form.cleaned_data["feedback"].strip()
        try:
            if decision == "approve":
                sub.approve(request.user, feedback)
                messages.success(
                    request, f"Approved. ${sub.reward} credited to {sub.user.username}."
                )
            elif decision == "reject":
                if not feedback:
                    form.add_error("feedback", "Please tell the artist why it was rejected.")
                    raise ValueError("feedback-missing")
                sub.reject(request.user, feedback)
                messages.info(request, "Submission rejected.")
            else:
                raise ValueError("bad-decision")
        except ValueError as exc:
            if str(exc) not in ("feedback-missing", "bad-decision"):
                messages.error(request, str(exc))
                return redirect("panel_review", pk=sub.pk)
            if str(exc) == "bad-decision":
                messages.error(request, "Choose approve or reject.")
        else:
            nxt = (
                Submission.objects.filter(status=Submission.Status.PENDING)
                .exclude(pk=sub.pk)
                .order_by("created_at")
                .first()
            )
            return redirect("panel_review", pk=nxt.pk) if nxt else redirect("panel_submissions")

    return render(request, "panel/review.html", {"sub": sub, "form": form})


@staff_required
def panel_tasks(request):
    qs = Task.objects.annotate(
        pending=Count("submissions", filter=Q(submissions__status=Submission.Status.PENDING)),
        total=Count("submissions"),
    )
    return render(
        request, "panel/tasks.html", {"page": paginate(request, qs, 12), "qs": query_without_page(request)}
    )


@staff_required
def panel_task_edit(request, pk=None):
    task = get_object_or_404(Task, pk=pk) if pk else None
    form = TaskForm(request.POST or None, request.FILES or None, instance=task)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        if not task:
            obj.created_by = request.user
        obj.save()
        messages.success(request, "Task saved." if task else "Task published to all users.")
        return redirect("panel_tasks")
    return render(request, "panel/task_form.html", {"form": form, "task": task})


@staff_required
@require_POST
def panel_task_toggle(request, pk):
    task = get_object_or_404(Task, pk=pk)
    task.is_active = not task.is_active
    task.save(update_fields=["is_active"])
    messages.success(request, f"“{task.title}” is now {'live' if task.is_active else 'hidden'}.")
    return redirect("panel_tasks")


@staff_required
def panel_users(request):
    q = request.GET.get("q", "").strip()
    qs = User.objects.filter(is_staff=False).select_related("profile").order_by("-profile__balance", "username")
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q))
    return render(
        request,
        "panel/users.html",
        {"page": paginate(request, qs, 15), "q": q, "qs": query_without_page(request)},
    )


@staff_required
def panel_user(request, pk):
    target = get_object_or_404(User, pk=pk)
    profile = get_profile(target)
    form = CreditForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        amount = form.cleaned_data["amount"]
        with transaction.atomic():
            profile = Profile.objects.select_for_update().get(pk=profile.pk)
            if profile.balance + amount < 0:
                form.add_error("amount", "That would take the balance below $0.00.")
            else:
                profile.balance += amount
                profile.save(update_fields=["balance"])
                PointTransaction.objects.create(
                    user=target,
                    amount=amount,
                    kind=(
                        PointTransaction.Kind.BONUS
                        if amount > 0
                        else PointTransaction.Kind.ADJUSTMENT
                    ),
                    note=form.cleaned_data["note"],
                    created_by=request.user,
                )
                messages.success(request, f"Dashboard updated for {target.username}.")
                return redirect("panel_user", pk=target.pk)
    return render(
        request,
        "panel/user_detail.html",
        {
            "target": target,
            "profile": profile,
            "form": form,
            "transactions": target.transactions.all()[:15],
            "submissions": target.submissions.select_related("task")[:8],
        },
    )


@staff_required
def panel_withdrawals(request):
    status = request.GET.get("status", Withdrawal.Status.PENDING)
    q = request.GET.get("q", "").strip()
    qs = Withdrawal.objects.select_related("user")
    if status in Withdrawal.Status.values:
        qs = qs.filter(status=status)
    else:
        status = "all"
    if q:
        qs = qs.filter(Q(user__username__icontains=q) | Q(payment_reference__icontains=q))
    if status == Withdrawal.Status.PENDING:
        qs = qs.order_by("created_at")  # oldest first
    return render(
        request,
        "panel/withdrawals.html",
        {
            "page": paginate(request, qs, 12),
            "status": status,
            "statuses": Withdrawal.Status.choices,
            "q": q,
            "qs": query_without_page(request),
        },
    )


@staff_required
def panel_withdrawal_review(request, pk):
    w = get_object_or_404(Withdrawal.objects.select_related("user"), pk=pk)
    form = WithdrawalReviewForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        decision = request.POST.get("decision")
        note = form.cleaned_data["note"].strip()
        reference = form.cleaned_data["payment_reference"].strip()
        try:
            if decision == "paid":
                if not reference:
                    form.add_error(
                        "payment_reference", "Add the transfer ID or transaction hash as proof of payment."
                    )
                    raise ValueError("form-error")
                w.mark_paid(request.user, reference, note)
                messages.success(request, f"Marked as paid. ${w.amount} sent to {w.user.username}.")
            elif decision == "reject":
                if not note:
                    form.add_error("note", "Tell the user why this was rejected.")
                    raise ValueError("form-error")
                w.reject(request.user, note)
                messages.info(request, f"Rejected. ${w.amount} returned to {w.user.username}'s balance.")
            else:
                messages.error(request, "Choose mark paid or reject.")
                raise ValueError("form-error")
        except ValueError as exc:
            if str(exc) != "form-error":
                messages.error(request, str(exc))
                return redirect("panel_withdrawal_review", pk=w.pk)
        else:
            return redirect("panel_withdrawals")
    return render(
        request,
        "panel/withdrawal_review.html",
        {"w": w, "form": form, "balance": get_profile(w.user).balance},
    )


@staff_required
def panel_deposits(request):
    status = request.GET.get("status", DepositRequest.Status.PENDING)
    q = request.GET.get("q", "").strip()
    qs = DepositRequest.objects.select_related("user")
    if status in DepositRequest.Status.values:
        qs = qs.filter(status=status)
    else:
        status = "all"
    if q:
        qs = qs.filter(Q(user__username__icontains=q) | Q(tx_hash__icontains=q))
    if status == DepositRequest.Status.PENDING:
        qs = qs.order_by("created_at")
    return render(
        request,
        "panel/deposits.html",
        {
            "page": paginate(request, qs, 12),
            "status": status,
            "statuses": DepositRequest.Status.choices,
            "q": q,
            "qs": query_without_page(request),
        },
    )


@staff_required
def panel_deposit_review(request, pk):
    d = get_object_or_404(DepositRequest.objects.select_related("user"), pk=pk)
    form = DepositReviewForm(request.POST or None, initial={"credited_amount": d.amount})
    if request.method == "POST" and form.is_valid():
        decision = request.POST.get("decision")
        note = form.cleaned_data["note"].strip()
        try:
            if decision == "credit":
                amount = form.cleaned_data["credited_amount"]
                if not amount:
                    form.add_error("credited_amount", "Enter the amount you verified on-chain.")
                    raise ValueError("form-error")
                d.approve(request.user, amount, note)
                messages.success(request, f"${amount} credited to {d.user.username}.")
            elif decision == "reject":
                if not note:
                    form.add_error("note", "Tell the user why this was rejected.")
                    raise ValueError("form-error")
                d.reject(request.user, note)
                messages.info(request, "Deposit claim rejected.")
            else:
                messages.error(request, "Choose credit or reject.")
                raise ValueError("form-error")
        except ValueError as exc:
            if str(exc) != "form-error":
                messages.error(request, str(exc))
                return redirect("panel_deposit_review", pk=d.pk)
        else:
            return redirect("panel_deposits")
    return render(
        request,
        "panel/deposit_review.html",
        {
            "d": d,
            "form": form,
            "balance": get_profile(d.user).balance,
            "address": configured_deposit_address(),
        },
    )


@staff_required
def panel_announcements(request):
    form = AnnouncementForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.created_by = request.user
        obj.save()
        messages.success(request, "Announcement posted to user dashboards.")
        return redirect("panel_announcements")
    return render(
        request,
        "panel/announcements.html",
        {"form": form, "items": Announcement.objects.all()[:30]},
    )


@staff_required
@require_POST
def panel_announcement_action(request, pk):
    item = get_object_or_404(Announcement, pk=pk)
    if request.POST.get("action") == "delete":
        item.delete()
        messages.info(request, "Announcement deleted.")
    else:
        item.is_active = not item.is_active
        item.save(update_fields=["is_active"])
        messages.success(request, "Announcement updated.")
    return redirect("panel_announcements")
