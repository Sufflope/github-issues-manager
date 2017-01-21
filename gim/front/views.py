from django.core.urlresolvers import reverse_lazy
from django.http import Http404, HttpResponseRedirect
from django.views.generic import DetailView, TemplateView

from gim.core.models import Issue
from gim.front.mixins.views import DependsOnSubscribedViewMixin


class HomeView(TemplateView):
    template_name = 'front/home.html'
    redirect_authenticated_url = reverse_lazy('front:dashboard:home')

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return HttpResponseRedirect(self.redirect_authenticated_url)
        return super(HomeView, self).get(request, *args, **kwargs)


class RedirectToIssueFromPK(DependsOnSubscribedViewMixin, DetailView):
    http_method_names = ['get']
    model = Issue
    pk_url_kwarg = 'issue_pk'
    url_name = 'issue-by-pk'

    def get_queryset(self):
        return super(RedirectToIssueFromPK, self).get_queryset().filter(repository__in=self.get_allowed_repositories())

    def render_to_response(self, context, **response_kwargs):
        return HttpResponseRedirect(context['issue'].get_absolute_url())

