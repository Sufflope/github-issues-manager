from django.conf.urls import url

from .views import GithubNotifications, GithubNotificationEditView, GithubNotificationsLastForMenu

urlpatterns = [
    url(r'^$', GithubNotifications.as_view(), name='home'),
    url(r'^last-for-menu/$', GithubNotificationsLastForMenu.as_view(), name='last'),
    url(r'^(?P<notif_id>\d+)/edit/$', GithubNotificationEditView.as_view(), name='edit'),
]
