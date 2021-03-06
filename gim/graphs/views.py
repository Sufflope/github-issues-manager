import json

from django.http import HttpResponse
from django.utils.cache import patch_response_headers
from django.views.generic.detail import BaseDetailView

from gim.core.models import Repository


class IssuesByDayForRepo(BaseDetailView):
    model = Repository
    http_method_names = ['get', ]
    pk_url_kwarg = 'repository_id'

    CACHE = 60 * 60 * 6  # 6 hours

    def get_context_data(self, **kwargs):
        context_data = super(IssuesByDayForRepo, self).get_context_data(**kwargs)

        data = self.object.graphs.get_issues_and_prs_by_day()

        height = float(self.request.GET.get('height', None) or 200)
        ratio = 1
        if data['max'] > height:
            ratio = height / data['max']
        elif data['max'] < height/2:
            ratio = 1

        context_data['max_height'] = int(round(data['max'] * ratio))
        context_data['graph_data'] = [(v1, v2) for d, v1, v2 in data['data']]
        context_data['dates'] = [str(d) for d, v1, v2 in data['data']]

        return context_data

    def render_to_response(self, context, **response_kwargs):
        json_data = json.dumps({
            'max_height': context['max_height'],
            'graph_data': context['graph_data'],
            'dates': context['dates'],
        })

        response = HttpResponse(
            json_data,
            content_type='application/json',
            **response_kwargs
        )

        # http cache for 15mn
        patch_response_headers(response, self.CACHE)
        return response
