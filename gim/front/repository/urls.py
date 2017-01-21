from django.conf.urls import include, url
from django.views.generic.base import RedirectView

from .views import (
    ToggleLocallyReviewedCommitFile,
    ToggleLocallyReviewedPullRequestFile,
)

urlpatterns = [
    url(r'^$', RedirectView.as_view(url='dashboard/', permanent=True), name='home'),
    url(r'^dashboard/', include('gim.front.repository.dashboard.urls')),
    url(r'^issues/', include('gim.front.repository.issues.urls')),
    url(r'^board/', include('gim.front.repository.board.urls')),

    url(r'^commit-file/(?P<file_pk>\d+)/toggle-reviewed/(?P<set_or_unset>set|unset)/(?:(?P<hunk_sha>[a-f0-9]{40})/)?$', ToggleLocallyReviewedCommitFile.as_view(), name=ToggleLocallyReviewedCommitFile.url_name),
    url(r'^pr-file/(?P<file_pk>\d+)/toggle-reviewed/(?P<set_or_unset>set|unset)/(?:(?P<hunk_sha>[a-f0-9]{40})/)?', ToggleLocallyReviewedPullRequestFile.as_view(), name=ToggleLocallyReviewedPullRequestFile.url_name),
]
