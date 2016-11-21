from django.conf.urls import patterns, include, url
from django.views.generic.base import RedirectView

from .views import ToggleLocallyReviewedCommitFile, ToggleLocallyReviewedPullRequestFile

urlpatterns = patterns('',
    url(r'^$', RedirectView.as_view(url='dashboard/'), name='home'),
    url(r'^dashboard/', include('gim.front.repository.dashboard.urls')),
    url(r'^issues/', include('gim.front.repository.issues.urls')),
    url(r'^board/', include('gim.front.repository.board.urls')),

    url(r'commit-file/(?P<file_pk>\d+)/toggle-reviewed/(?P<set_or_unset>set|unset)/$', ToggleLocallyReviewedCommitFile.as_view(), name=ToggleLocallyReviewedCommitFile.url_name),
    url(r'pr-file/(?P<file_pk>\d+)/toggle-reviewed/(?P<set_or_unset>set|unset)/', ToggleLocallyReviewedPullRequestFile.as_view(), name=ToggleLocallyReviewedPullRequestFile.url_name),
)
