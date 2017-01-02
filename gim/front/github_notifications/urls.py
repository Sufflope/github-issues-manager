from django.conf.urls import url

from .views import GithubNotifications, GithubNotificationEditView

urlpatterns = [
    url(r'^$', GithubNotifications.as_view(), name='home'),
    url(r'^(?P<notif_id>\d+)/edit/$', GithubNotificationEditView.as_view(), name='edit'),
]
