from django.conf.urls import include, url
from django.contrib.auth.decorators import login_required

from decorator_include import decorator_include

from gim.front.views import HomeView, RedirectToIssueFromPK

urlpatterns = [
    url(r'^$', HomeView.as_view(), name='home'),
    url(r'^auth/', include('gim.front.auth.urls', namespace='auth')),
    url(r'^github-notifications/', decorator_include(login_required, u'gim.front.github_notifications.urls', namespace='github-notifications')),
    url(r'^dashboard/', decorator_include(login_required, u'gim.front.dashboard.urls', namespace='dashboard')),
    url(r'^issue/(?P<issue_pk>\d+)/$', login_required(RedirectToIssueFromPK.as_view()), name=RedirectToIssueFromPK.url_name),
    url(r'^(?P<owner_username>[^/]+)/(?P<repository_name>[^/]+)/', decorator_include(login_required, u'gim.front.repository.urls', namespace='repository')),
]
