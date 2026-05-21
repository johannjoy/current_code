from django.contrib import admin
from django.urls import path, include
from platform_app import views 
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.waiting_room, name='waiting_room'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('home/', views.home, name='home'),
    path('problem/<int:problem_id>/', views.problem_detail, name='problem_detail'),
    path('api/save/', views.save_code),
    path('leaderboard/', views.leaderboard, name='leaderboard'),
    path('api/load/<int:problem_id>/', views.load_code),
    path('api/run-custom/', views.run_code_custom, name='run_custom'),
    path('api/submit/', views.submit_code, name='submit_code'),
    path('check-status/', views.check_hackathon_status, name='check_status'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('api/status/', views.check_hackathon_status, name='check_status'),
    path('finished/', views.finished, name='finished'),
    path('api/bonus/status/', views.bonus_status, name='bonus_status'),
    path('api/bonus/submit/', views.bonus_submit, name='bonus_submit'),
    path('api/leaderboard-data/', views.leaderboard_data, name='leaderboard_data'),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)