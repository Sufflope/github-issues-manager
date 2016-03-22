from django.conf.urls import patterns, include, url

from .views import GithubNotifications, GithubNotificationEditView

urlpatterns = patterns('',
    url(r'^$', GithubNotifications.as_view(), name='home'),
    url(r'^(?P<notif_id>\d+)/edit/$', GithubNotificationEditView.as_view(), name='edit'),
)
