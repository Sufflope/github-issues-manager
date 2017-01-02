from django.conf.urls import url

from .views import IssuesByDayForRepo

urlpatterns = [
    url(r'^issues-by-day/(?P<repository_id>\d+)/', IssuesByDayForRepo.as_view(), name='issues_by_day_for_repo'),
]
