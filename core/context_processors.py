from .models import DepositRequest, Submission, Withdrawal


def staff_badges(request):
    """Adds pending counts (drawings, withdrawals) to the nav for staff users."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.is_staff:
        return {
            "pending_review_count": Submission.objects.filter(
                status=Submission.Status.PENDING
            ).count(),
            "pending_withdrawal_count": Withdrawal.objects.filter(
                status=Withdrawal.Status.PENDING
            ).count(),
            "pending_deposit_count": DepositRequest.objects.filter(
                status=DepositRequest.Status.PENDING
            ).count(),
        }
    return {}
