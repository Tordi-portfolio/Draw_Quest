from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import StyledAuthForm

urlpatterns = [
    path("", views.home, name="home"),
    # auth
    path("signup/", views.signup, name="signup"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            authentication_form=StyledAuthForm,
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    # user area
    path("tasks/", views.task_list, name="tasks"),
    path("tasks/<int:pk>/", views.task_detail, name="task_detail"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("submissions/", views.my_submissions, name="my_submissions"),
    path("profile/", views.profile_edit, name="profile"),
    path("withdraw/", views.withdraw, name="withdraw"),
    path("deposit/", views.deposit, name="deposit"),
    # admin panel (staff only)
    path("panel/", views.panel_home, name="panel_home"),
    path("panel/submissions/", views.panel_submissions, name="panel_submissions"),
    path("panel/submissions/<int:pk>/", views.panel_review, name="panel_review"),
    path("panel/tasks/", views.panel_tasks, name="panel_tasks"),
    path("panel/tasks/new/", views.panel_task_edit, name="panel_task_new"),
    path("panel/tasks/<int:pk>/edit/", views.panel_task_edit, name="panel_task_edit"),
    path("panel/tasks/<int:pk>/toggle/", views.panel_task_toggle, name="panel_task_toggle"),
    path("panel/users/", views.panel_users, name="panel_users"),
    path("panel/users/<int:pk>/", views.panel_user, name="panel_user"),
    path("panel/deposits/", views.panel_deposits, name="panel_deposits"),
    path("panel/deposits/<int:pk>/", views.panel_deposit_review, name="panel_deposit_review"),
    path("panel/withdrawals/", views.panel_withdrawals, name="panel_withdrawals"),
    path(
        "panel/withdrawals/<int:pk>/",
        views.panel_withdrawal_review,
        name="panel_withdrawal_review",
    ),
    path("panel/announcements/", views.panel_announcements, name="panel_announcements"),
    path(
        "panel/announcements/<int:pk>/action/",
        views.panel_announcement_action,
        name="panel_announcement_action",
    ),
]
