from django.conf.urls import patterns, url

from .views import (DashboardView, MilestonesPart, CountersPart, LabelsPart,
                    LabelsEditor, LabelTypeCreate, LabelTypeEdit,
                    LabelTypePreview, LabelTypeDelete, LabelCreate,
                    LabelEdit, LabelDelete)

urlpatterns = patterns('',
    url(r'^$', DashboardView.as_view(), name=DashboardView.url_name),
    url(r'^milestones/$', MilestonesPart.as_view(), name=MilestonesPart.url_name),
    url(r'^counters/$', CountersPart.as_view(), name=CountersPart.url_name),
    url(r'^labels/$', LabelsPart.as_view(), name=LabelsPart.url_name),

    url(r'^labels/editor/$', LabelsEditor.as_view(), name=LabelsEditor.url_name),
    url(r'^labels/editor/group/create/$', LabelTypeCreate.as_view(), name=LabelTypeCreate.url_name),
    url(r'^labels/editor/group/(?P<label_type_id>\d+)/edit/$', LabelTypeEdit.as_view(), name=LabelTypeEdit.url_name),
    url(r'^labels/editor/group/(?P<label_type_id>\d+)/delete/$', LabelTypeDelete.as_view(), name=LabelTypeDelete.url_name),
    url(r'^labels/editor/group/preview/$', LabelTypePreview.as_view(), name=LabelTypePreview.url_name),
    url(r'^labels/editor/label/create/$', LabelCreate.as_view(), name=LabelCreate.url_name),
    url(r'^labels/editor/label/(?P<label_id>\d+)/edit/$', LabelEdit.as_view(), name=LabelEdit.url_name),
    url(r'^labels/editor/label/(?P<label_id>\d+)/delete/$', LabelDelete.as_view(), name=LabelDelete.url_name),
)
