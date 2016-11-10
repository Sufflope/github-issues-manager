from django.conf.urls import patterns, url

from .views import (
    BoardSelectorView, BoardView, BoardColumnView, BoardProjectColumnView,
    BoardMoveIssueView, BoardCanMoveIssueView,
    BoardCanMoveProjectCardView, BoardMoveProjectCardView,
    CardNoteCreateView, CardNoteView, CardNoteEditView, CardNoteDeleteView,
    ColumnCreateView, ColumnEditView, ColumnDeleteView,
    ColumnInfoView, ColumnMoveView, ColumnCanMoveView
)

urlpatterns = patterns('',
    # main view
    url(r'^(?P<board_mode>auto|labels|project)/(?P<board_key>[^/]+)/$', BoardView.as_view(), name=BoardView.url_name),

    url(r'^$', BoardSelectorView.as_view(), name=BoardSelectorView.url_name),
    # project real column
    url(r'^(?P<board_mode>project)/(?P<board_key>[^/]+)/(?P<column_key>\d+)/$', BoardProjectColumnView.as_view(), name=BoardProjectColumnView.url_name),
    # move to A project column or the "not in project" column
    url(r'^(?P<board_mode>project)/(?P<board_key>[^/]+)/(?P<column_key>[^/]+)/can_move/(?P<is_note>note-)?(?P<issue_number>\d+)/$', BoardCanMoveProjectCardView.as_view(), name=BoardCanMoveProjectCardView.url_name),
    url(r'^(?P<board_mode>project)/(?P<board_key>[^/]+)/(?P<column_key>[^/]+)/move/(?P<is_note>note-)?(?P<issue_number>\d+)/to/(?P<to_column_key>[^/]+)/$', BoardMoveProjectCardView.as_view(), name=BoardMoveProjectCardView.url_name),

    # columns not related to A project, or "not in project" column
    url(r'^(?P<board_mode>auto|labels|project)/(?P<board_key>[^/]+)/(?P<column_key>[^/]+)/$', BoardColumnView.as_view(), name=BoardColumnView.url_name),
    # move to columns not related to a project
    url(r'^(?P<board_mode>auto|labels)/(?P<board_key>[^/]+)/(?P<column_key>[^/]+)/can_move/(?P<issue_number>\d+)/$', BoardCanMoveIssueView.as_view(), name=BoardCanMoveIssueView.url_name),
    url(r'^(?P<board_mode>auto|labels)/(?P<board_key>[^/]+)/(?P<column_key>[^/]+)/move/(?P<issue_number>\d+)/to/(?P<to_column_key>[^/]+)/$', BoardMoveIssueView.as_view(), name=BoardMoveIssueView.url_name),

    # project column edit
    url(r'project/(?P<project_number>\d+)/column/add/$', ColumnCreateView.as_view(), name=ColumnCreateView.url_name),
    url(r'project/(?P<project_number>\d+)/column/(?P<column_id>\d+)/info/$', ColumnInfoView.as_view(), name=ColumnInfoView.url_name),
    url(r'project/(?P<project_number>\d+)/column/(?P<column_id>\d+)/edit/$', ColumnEditView.as_view(), name=ColumnEditView.url_name),
    url(r'project/(?P<project_number>\d+)/column/(?P<column_id>\d+)/delete/$', ColumnDeleteView.as_view(), name=ColumnDeleteView.url_name),

    # project column move
    url(r'project/(?P<project_number>\d+)/column/(?P<column_id>\d+)/can_move/$', ColumnCanMoveView.as_view(), name=ColumnCanMoveView.url_name),
    url(r'project/(?P<project_number>\d+)/column/(?P<column_id>\d+)/move/to/$', ColumnMoveView.as_view(), name=ColumnMoveView.url_name),

    # card note edit
    url(r'project/(?P<project_number>\d+)/(?P<column_id>\d+)/note/add/$', CardNoteCreateView.as_view(), name=CardNoteCreateView.url_name),
    url(r'project/(?P<project_number>\d+)/note/(?P<card_pk>\d+)/$', CardNoteView.as_view(), name=CardNoteView.url_name),
    url(r'project/(?P<project_number>\d+)/note/(?P<card_pk>\d+)/edit/$', CardNoteEditView.as_view(), name=CardNoteEditView.url_name),
    url(r'project/(?P<project_number>\d+)/note/(?P<card_pk>\d+)/delete/$', CardNoteDeleteView.as_view(), name=CardNoteDeleteView.url_name),
)
