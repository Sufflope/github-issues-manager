from django.conf.urls import patterns, url

from .views import BoardView, BoardColumnView

urlpatterns = patterns('',
    url(r'^(?:(?P<board_mode>auto|labels)/(?P<board_key>[^/]+)/)?$', BoardView.as_view(), name=BoardView.url_name),
    url(r'^(?P<board_mode>auto|labels)/(?P<board_key>[^/]+)/(?P<column_key>[^/]+)/$', BoardColumnView.as_view(), name=BoardColumnView.url_name),
)
