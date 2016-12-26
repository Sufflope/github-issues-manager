from django.conf.urls import include, url

from gim.front.activity.urls import activity_pattern

from .views import DashboardHome, DashboardActivityPart

urlpatterns = [
    url(r'^$', DashboardHome.as_view(), name='home'),
    url(activity_pattern, DashboardActivityPart.as_view(), name='activity'),
    url(r'^repositories/', include('gim.front.dashboard.repositories.urls', namespace='repositories')),
]
