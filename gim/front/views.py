from django.core.urlresolvers import reverse_lazy
from django.http import Http404, HttpResponseRedirect
from django.utils.functional import cached_property
from django.views.generic import DetailView, TemplateView

from gim.core.models import Issue
from gim.front.mixins.views import WithIssueViewMixin


class HomeView(TemplateView):
    template_name = 'front/home.html'
    redirect_authenticated_url = reverse_lazy('front:dashboard:home')

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return HttpResponseRedirect(self.redirect_authenticated_url)
        return super(HomeView, self).get(request, *args, **kwargs)


class RedirectToIssueFromPK(WithIssueViewMixin, DetailView):
    http_method_names = ['get']
    model = Issue
    pk_url_kwarg = 'issue_pk'
    url_name = 'issue-by-pk'

    @cached_property
    def issue(self):
        return self.object

    @cached_property
    def repository(self):
        return self.issue.repository

    def render_to_response(self, context, **response_kwargs):
        if not self.is_repository_allowed(self.repository):
            raise Http404
        return HttpResponseRedirect(self.issue.get_absolute_url())

