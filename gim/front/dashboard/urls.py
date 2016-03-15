from django.conf.urls import patterns, include, url

from gim.front.activity.urls import activity_pattern

from .views import DashboardHome, DashboardActivityPart, GithubNotifications

urlpatterns = patterns('',
    url(r'^$', DashboardHome.as_view(), name='home'),
    url(r'^github-notifications/', GithubNotifications.as_view(), name='github-notifications'),
    url(activity_pattern, DashboardActivityPart.as_view(), name='activity'),
    url(r'^repositories/', include('gim.front.dashboard.repositories.urls', namespace='repositories')),
)
