from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),  # 👈 Root URL shows login page
    path('landing_page/', views.landing_page, name='landing_page'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('workspace/', views.employee_workspace, name='workspace'),
    # path('contribute/', views.contribute_workspace, name='contribute'),
    path('dashboard/admin/', views.admin_dashboard, name='admin_dashboard'),
    path('leaderboard/', views.leaderboard, name='leaderboard'),
    path('employee_workspace/', views.employee_workspace, name='employee_workspace'),
    path('contribute_workspace/', views.contribute_workspace, name='contribute_workspace'),
    path('api/leaderboard/', views.api_leaderboard, name='api_leaderboard'),
    path('login/', views.login_view, name='login'),
    path('contribute/submit/', views.contribute_submit, name='contribute_submit'),
    path('admin/delete_user/<int:user_id>/', views.admin_delete_user, name='admin_delete_user'),
    path('api/stats/', views.api_stats, name='api_stats'),
    path('api/stats/contribution/', views.api_stats_contribution, name='api_stats_contribution'),
    path('api/review_files/', views.api_review_files, name='api_review_files'),
    path('api/locked_files/', views.api_locked_files, name='api_locked_files'),
    path('api/contribution_reviews/', views.api_contribution_reviews, name='api_contribution_reviews'),
    path('admin/verify_all_transcription/', views.admin_verify_all_transcription, name='admin_verify_all_transcription'),
    path('admin/release_locks/', views.admin_release_locks, name='admin_release_locks'),



]
