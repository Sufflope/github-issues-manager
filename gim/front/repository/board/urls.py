from django.conf.urls import patterns, url

from .views import (
    BoardSelectorView, BoardView, BoardColumnView,
    BoardMoveIssueView, BoardCanMoveIssueView,
    BoardCanMoveProjectCardView, BoardMoveProjectCardView
)

urlpatterns = patterns('',
                       url(r'^$', BoardSelectorView.as_view(), name=BoardSelectorView.url_name),
                       url(r'^(?P<board_mode>auto|labels|project)/(?P<board_key>[^/]+)/$', BoardView.as_view(), name=BoardView.url_name),
                       url(r'^(?P<board_mode>auto|labels|project)/(?P<board_key>[^/]+)/(?P<column_key>[^/]+)/$', BoardColumnView.as_view(), name=BoardColumnView.url_name),
                       url(r'^(?P<board_mode>auto|labels)/(?P<board_key>[^/]+)/can_move/(?P<issue_number>\d+)/$', BoardCanMoveIssueView.as_view(), name=BoardCanMoveIssueView.url_name),
                       url(r'^(?P<board_mode>auto|labels)/(?P<board_key>[^/]+)/(?P<column_key>[^/]+)/move/(?P<issue_number>\d+)/to/(?P<to_column_key>[^/]+)/$', BoardMoveIssueView.as_view(), name=BoardMoveIssueView.url_name),
                       url(r'^(?P<board_mode>project)/(?P<board_key>[^/]+)/can_move/(?P<issue_number>\d+)/$', BoardCanMoveProjectCardView.as_view(), name=BoardCanMoveProjectCardView.url_name),
                       url(r'^(?P<board_mode>project)/(?P<board_key>[^/]+)/(?P<column_key>[^/]+)/move/(?P<issue_number>\d+)/to/(?P<to_column_key>[^/]+)/$', BoardMoveProjectCardView.as_view(), name=BoardMoveProjectCardView.url_name),
                       )
