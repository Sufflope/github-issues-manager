from django.conf.urls import url

from gim.front.repository.issues.multiselect.views import (
    MultiSelectListAssigneesView,
    MultiSelectListLabelsView,
    MultiSelectListMilestonesView,
    MultiSelectListProjectsView,
    MultiSelectListStatesView,
    MultiSelectApplyAssigneesView,
    MultiSelectApplyLabelsView,
    MultiSelectApplyMilestoneView,
    MultiSelectApplyProjectsView,
    MultiSelectApplyStateView,
)

urlpatterns = [
    url(r'^assignees/list/$', MultiSelectListAssigneesView.as_view(), name=MultiSelectListAssigneesView.url_name),
    url(r'^labels/list/$', MultiSelectListLabelsView.as_view(), name=MultiSelectListLabelsView.url_name),
    url(r'^milestone/list/$', MultiSelectListMilestonesView.as_view(), name=MultiSelectListMilestonesView.url_name),
    url(r'^projects/list/$', MultiSelectListProjectsView.as_view(), name=MultiSelectListProjectsView.url_name),
    url(r'^state/list/$', MultiSelectListStatesView.as_view(), name=MultiSelectListStatesView.url_name),
    url(r'^assignees/apply/$', MultiSelectApplyAssigneesView.as_view(), name=MultiSelectApplyAssigneesView.url_name),
    url(r'^labels/apply/$', MultiSelectApplyLabelsView.as_view(), name=MultiSelectApplyLabelsView.url_name),
    url(r'^milestone/apply/$', MultiSelectApplyMilestoneView.as_view(), name=MultiSelectApplyMilestoneView.url_name),
    url(r'^projects/apply/$', MultiSelectApplyProjectsView.as_view(), name=MultiSelectApplyProjectsView.url_name),
    url(r'^state/apply/$', MultiSelectApplyStateView.as_view(), name=MultiSelectApplyStateView.url_name),
]
