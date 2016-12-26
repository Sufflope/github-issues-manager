from django.conf.urls import url

from .views import GithubWebHook

urlpatterns = [
    url(r'^github/web/', GithubWebHook.as_view(), name='github_web'),
]
