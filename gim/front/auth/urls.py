from django.conf.urls import url

from .views import LoginView, ConfirmView, LogoutView

urlpatterns = [
    url(r'^$', LoginView.as_view(), name='login'),
    url(r'^confirm/$', ConfirmView.as_view(), name='confirm'),
    url(r'^logout/$', LogoutView.as_view(), name='logout'),
]
